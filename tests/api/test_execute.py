"""Tests de la ejecución de una herramienta — `POST /tools/{name}/execute`.

Mismo montaje que el catálogo: se sustituye `mcp_session._http_client` por uno
sobre `ASGITransport`, así que el protocolo se habla entero en el mismo proceso
y sin abrir puertos. Se usan sólo tools locales y deterministas: nada de red.
"""

from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api import execute
from backend.api.app import app as api_app
from backend.api.schemas import ExecuteStatus
from backend.config.settings import settings
from backend.core.mcp import session as mcp_session
from backend.core.mcp.tools import InvalidArguments, ToolNotFound
from backend.core.models import ToolResult

_BASE = "http://127.0.0.1:8765"
_URL = f"{_BASE}/mcp"

# Un servidor MCP caído: el puerto 1 está cerrado, así que la conexión se
# rechaza al momento, sin red de verdad y sin esperar a ningún corte.
_CAIDO = "http://127.0.0.1:1/mcp"


class _TransporteMixto(httpx.AsyncBaseTransport):
    """El servidor en proceso para su dirección, y la red de verdad para las demás.

    Así un servidor caído falla como en producción —httpx no puede conectar y el
    cliente MCP lo envuelve en sus grupos— y no con una excepción fabricada, que
    es la trampa de #187: respx sustituye la causa, y la cadena que llega no es
    la de verdad.
    """

    def __init__(self, app):
        self._en_proceso = httpx.ASGITransport(app=app)
        self._red = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.port == 8765:
            return await self._en_proceso.handle_async_request(request)
        return await self._red.handle_async_request(request)

    async def aclose(self) -> None:
        await self._en_proceso.aclose()
        await self._red.aclose()


@asynccontextmanager
async def servidor_en_proceso(monkeypatch, mcp, servidores=(_URL,)):
    app = mcp.streamable_http_app()

    # El gestor de sesiones de FastMCP arranca en el lifespan de la app, y
    # ASGITransport no lo ejecuta: hay que entrarlo a mano.
    async with app.router.lifespan_context(app):
        monkeypatch.setattr(
            mcp_session,
            "_http_client",
            lambda _timeout: httpx.AsyncClient(
                transport=_TransporteMixto(app), base_url=_BASE
            ),
        )
        monkeypatch.setattr(settings, "mcp_servers", list(servidores))
        yield


async def _ejecutar(monkeypatch, mcp, nombre, argumentos, servidores=(_URL,)):
    """Ejecuta dentro del servidor en proceso y relanza los fallos FUERA.

    Si una excepción escapara atravesando `lifespan_context`, anyio la
    envolvería en un `ExceptionGroup` —el *lifespan* abre un task group— y
    `pytest.raises(InvalidArguments)` no la reconocería. Es artefacto del
    andamiaje, no del código: en producción la ruta no corre dentro del ciclo de
    vida del servidor MCP.
    """
    resultado = fallo = None
    async with servidor_en_proceso(monkeypatch, mcp, servidores):
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
    # Las cinco fichas en inglés, y en español la del lineal (#231) y la de la
    # dedicada (#242) y la del tono (#233).
    assert len(resultado.data["result"]) == 8


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


@pytest.mark.asyncio
async def test_el_motivo_llega_sin_el_prefijo_en_ingles_de_fastmcp(
    monkeypatch, servidor_mcp
):
    """#191: FastMCP antepone «Error executing tool <nombre>: » al mensaje de
    una herramienta que falla. El mensaje ya es público y está en castellano;
    el prefijo sólo repite el nombre en otro idioma, y salía por aquí, por la
    pantalla de Sistema y por la traza del agente."""
    resultado = await _ejecutar(
        monkeypatch, servidor_mcp, "detect_clickbait_lexical", {"headline": "   "}
    )

    assert resultado.detail is not None
    assert not resultado.detail.startswith("Error executing tool")
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


# ----- Un servidor MCP que no responde (R1.8, #292) -----


@pytest.mark.asyncio
async def test_un_servidor_caido_delante_no_impide_ejecutar(monkeypatch, servidor_mcp):
    """Con varios servidores, la herramienta se busca en orden. Hasta #292, uno
    caído delante cortaba la búsqueda con su error de conexión, y nunca se
    llegaba al que la tiene: R1.8 pide seguir operando con los restantes."""
    resultado = await _ejecutar(
        monkeypatch,
        servidor_mcp,
        "detect_clickbait_lexical",
        {"headline": "You Won't Believe What Happened Next"},
        servidores=(_CAIDO, _URL),
    )

    assert resultado.status == ExecuteStatus.OK


@pytest.mark.asyncio
async def test_sin_la_herramienta_y_con_un_servidor_caido_no_es_un_404(
    monkeypatch, servidor_mcp
):
    """Si la herramienta no está en los que respondieron, puede estar en el que
    no respondió: decir que no existe sería falso. Se dice que no responde."""
    from backend.core.mcp.tools import ServerUnavailable

    with pytest.raises(ServerUnavailable):
        await _ejecutar(
            monkeypatch, servidor_mcp, "no_existe", {}, servidores=(_URL, _CAIDO)
        )


def test_con_el_unico_servidor_caido_es_un_503_con_una_frase_publica(monkeypatch):
    """Hasta #292 era un 500 en texto plano: el error de conexión llega dentro de
    un `ExceptionGroup` y nadie lo capturaba. Es un 503, «el servicio no está
    disponible ahora», y la frase no nombra la excepción (#163)."""
    monkeypatch.setattr(settings, "mcp_servers", [_CAIDO])
    cliente = TestClient(api_app, raise_server_exceptions=False)

    respuesta = cliente.post(
        "/tools/detect_clickbait_lexical/execute",
        json={"arguments": {"headline": "You Won't Believe What Happened Next"}},
    )

    assert respuesta.status_code == 503
    detalle = respuesta.json()["detail"]
    assert "no responde" in detalle
    assert "ConnectError" not in detalle
    assert "TaskGroup" not in detalle


# ----- El texto vacío (R3.5) y lo que no se publica (R12.7), #292 -----


class _ModeloQueApunta:
    """Un backend NLP que apunta con qué texto lo llaman, sin cargar nada."""

    def __init__(self):
        self.textos: list[str] = []

    async def classify(self, text: str, model: str) -> ToolResult:
        self.textos.append(text)
        return ToolResult.ok({"label": "neutral", "score": 0.5})


class _DetectorQueApunta:
    """Un detector de incoherencia que apunta con qué titular lo llaman."""

    def __init__(self):
        self.titulares: list[str] = []

    async def detect(self, headline: str, content: str) -> ToolResult:
        self.titulares.append(headline)
        return ToolResult.ok(
            {
                "similarity": 0.5,
                "incoherent": False,
                "threshold": 0.3,
                "headline": headline,
                "content": content,
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("texto", ["", "   "])
async def test_el_tono_rechaza_el_texto_vacio_sin_llamar_al_modelo(
    monkeypatch, servidor_mcp, texto
):
    """Hasta #292, `analyze_sentiment` clasificaba la cadena vacía: el detector
    de idioma la daba por inglés y el modelo devolvía una etiqueta de nada."""
    modelo = _ModeloQueApunta()
    monkeypatch.setattr("backend.integrations.nlp.tool.get_nlp_backend", lambda: modelo)

    resultado = await _ejecutar(
        monkeypatch, servidor_mcp, "analyze_sentiment", {"text": texto}
    )

    assert resultado.status == ExecuteStatus.ERROR
    assert resultado.detail == "El texto está vacío o no es válido"
    assert modelo.textos == []


@pytest.mark.asyncio
@pytest.mark.parametrize("titular", ["", "   "])
async def test_la_incoherencia_rechaza_el_titular_vacio_sin_llamar_al_modelo(
    monkeypatch, servidor_mcp, titular
):
    """Hasta #292 calculaba la similitud entre un titular vacío y el cuerpo."""
    detector = _DetectorQueApunta()
    monkeypatch.setattr(
        "backend.integrations.nlp.tool.get_incoherence_detector",
        lambda _idioma: detector,
    )

    resultado = await _ejecutar(
        monkeypatch,
        servidor_mcp,
        "detect_clickbait_incoherence",
        {
            "headline": titular,
            "content": "The central bank kept interest rates unchanged on Tuesday.",
        },
    )

    assert resultado.status == ExecuteStatus.ERROR
    assert resultado.detail == "El titular está vacío o no es válido"
    assert detector.titulares == []


@pytest.mark.asyncio
@pytest.mark.parametrize("titular", ["", "   "])
async def test_el_analisis_completo_rechaza_el_titular_vacio_con_su_frase(
    monkeypatch, servidor_mcp, titular
):
    """Hasta #292, `analyze_headline` con un titular en blanco publicaba el error
    de validación de Pydantic entero: el nombre del modelo, la regla y la
    dirección de su documentación. Es el caso de R12.7 que se veía hoy."""
    resultado = await _ejecutar(
        monkeypatch, servidor_mcp, "analyze_headline", {"headline": titular}
    )

    assert resultado.status == ExecuteStatus.ERROR
    assert resultado.detail == "El titular está vacío o no es válido"
    assert "AnalyzeRequest" not in resultado.detail


# ----- Los argumentos, en la respuesta y con ella en el historial (R9.2, #292) -----


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "titular", ["You Won't Believe What Happened Next", "   "], ids=["ok", "error"]
)
async def test_la_respuesta_lleva_sus_argumentos(monkeypatch, servidor_mcp, titular):
    """R9.2 pide guardar los parámetros de cada ejecución, y el historial guarda
    la respuesta: hasta #292, un `get_guardian_news` no decía qué se buscó. Van
    también cuando la herramienta falla, que es cuando más hacen falta."""
    argumentos = {"headline": titular}

    resultado = await _ejecutar(
        monkeypatch, servidor_mcp, "detect_clickbait_lexical", argumentos
    )

    assert resultado.arguments == argumentos
