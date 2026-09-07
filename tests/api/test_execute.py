"""Tests de la ejecución de una herramienta — `POST /tools/{name}/execute`.

Mismo montaje que el catálogo: se sustituye `mcp_session._http_client` por uno
sobre `ASGITransport`, así que el protocolo se habla entero en el mismo proceso
y sin abrir puertos. Se usan sólo tools locales y deterministas: nada de red.
"""

from contextlib import asynccontextmanager

import httpx
import pytest

from backend.api import execute
from backend.api.schemas import ExecuteStatus
from backend.config.settings import settings
from backend.core.mcp import session as mcp_session
from backend.core.mcp.tools import InvalidArguments, ToolNotFound

_BASE = "http://127.0.0.1:8765"
_URL = f"{_BASE}/mcp"


@asynccontextmanager
async def servidor_en_proceso(monkeypatch, mcp):
    app = mcp.streamable_http_app()

    # El gestor de sesiones de FastMCP arranca en el lifespan de la app, y
    # ASGITransport no lo ejecuta: hay que entrarlo a mano.
    async with app.router.lifespan_context(app):
        monkeypatch.setattr(
            mcp_session,
            "_http_client",
            lambda _timeout: httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=_BASE
            ),
        )
        monkeypatch.setattr(settings, "mcp_servers", [_URL])
        yield


async def _ejecutar(monkeypatch, mcp, nombre, argumentos):
    """Ejecuta dentro del servidor en proceso y relanza los fallos FUERA.

    Si una excepción escapara atravesando `lifespan_context`, anyio la
    envolvería en un `ExceptionGroup` —el *lifespan* abre un task group— y
    `pytest.raises(InvalidArguments)` no la reconocería. Es artefacto del
    andamiaje, no del código: en producción la ruta no corre dentro del ciclo de
    vida del servidor MCP.
    """
    resultado = fallo = None
    async with servidor_en_proceso(monkeypatch, mcp):
        try:
            resultado = await execute.execute_tool(nombre, argumentos)
        except Exception as exc:  # se relanza intacta más abajo
            fallo = exc

    if fallo is not None:
        raise fallo
    return resultado


# ----- Camino correcto -----


@pytest.mark.asyncio
async def test_ejecuta_y_devuelve_datos_estructurados(monkeypatch, servidor_mcp):
    resultado = await _ejecutar(
        monkeypatch,
        servidor_mcp,
        "detect_clickbait_lexical",
        {"headline": "10 Things You Won't Believe"},
    )

    assert resultado.status == ExecuteStatus.OK
    assert resultado.tool == "detect_clickbait_lexical"
    assert resultado.server == "tfg-mcp-server"
    # Estructurado, no una cadena que haya que parsear.
    assert resultado.data["is_clickbait"] is True
    assert resultado.detail is None


@pytest.mark.asyncio
async def test_una_salida_de_texto_llega_envuelta_en_result(monkeypatch, servidor_mcp):
    # `describe_models` devuelve una lista, y el protocolo sólo deja sin
    # envolver los objetos: por eso llega bajo `result`. No es una carencia.
    resultado = await _ejecutar(monkeypatch, servidor_mcp, "describe_models", {})

    assert resultado.status == ExecuteStatus.OK
    assert len(resultado.data["result"]) == 5


# ----- La herramienta se ejecuta y falla: 200 con status error -----


@pytest.mark.asyncio
async def test_un_fallo_de_la_tool_no_es_un_error_http(monkeypatch, servidor_mcp):
    """La petición era correcta y el servidor la atendió; lo que falló es el
    análisis. Mismo criterio que en `/analyze`, donde una señal caída no tumba
    la respuesta.

    Esto sólo se puede distinguir desde que las tools **lanzan** en vez de
    devolver el error: antes llegaba por el mismo canal que un resultado válido.
    """
    resultado = await _ejecutar(
        monkeypatch, servidor_mcp, "detect_clickbait_lexical", {"headline": "   "}
    )

    assert resultado.status == ExecuteStatus.ERROR
    assert resultado.data is None
    # El motivo real, no una queja genérica.
    assert "vacío" in resultado.detail


# ----- Errores de la petición -----


@pytest.mark.asyncio
async def test_una_herramienta_inexistente_es_404(monkeypatch, servidor_mcp):
    with pytest.raises(ToolNotFound):
        await _ejecutar(monkeypatch, servidor_mcp, "no_existe", {})


@pytest.mark.asyncio
async def test_un_argumento_que_falta_es_422(monkeypatch, servidor_mcp):
    with pytest.raises(InvalidArguments, match="headline"):
        await _ejecutar(monkeypatch, servidor_mcp, "detect_clickbait_lexical", {})


@pytest.mark.asyncio
async def test_un_argumento_del_tipo_equivocado_es_422(monkeypatch, servidor_mcp):
    with pytest.raises(InvalidArguments):
        await _ejecutar(
            monkeypatch, servidor_mcp, "detect_clickbait_lexical", {"headline": 42}
        )


@pytest.mark.asyncio
async def test_se_acumulan_todos_los_problemas_de_validacion(monkeypatch, servidor_mcp):
    """Quien rellena un formulario prefiere corregirlo de una vez a descubrir
    los errores de uno en uno."""
    with pytest.raises(InvalidArguments) as error:
        await _ejecutar(
            monkeypatch,
            servidor_mcp,
            "get_nyt_news",
            {"topic": 1, "days": 999},  # tipo malo y fuera de rango
        )

    assert "topic" in str(error.value)
    assert "days" in str(error.value)


@pytest.mark.asyncio
async def test_la_validacion_ocurre_antes_de_invocar(monkeypatch, servidor_mcp):
    """R4.5. Importa que sea *antes*: si validara MCP, un argumento mal escrito
    llegaría como fallo de ejecución y sería indistinguible de un análisis que
    salió mal — 200 con status error en vez del 422 que corresponde.
    """
    with pytest.raises(InvalidArguments):
        await _ejecutar(
            monkeypatch, servidor_mcp, "detect_clickbait_lexical", {"headline": None}
        )
