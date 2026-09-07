"""Tests del catálogo — `GET /tools`.

Ninguno abre un puerto. Se sustituye `catalog._http_client` por uno montado
sobre `ASGITransport` contra la app MCP real: el protocolo se habla entero
—handshake, `list_tools`— en el mismo proceso. Es el mismo truco de
`test_main.py`, y aquí es además necesario, porque el servidor arranca por
defecto en `stdio` y no hay nada escuchando en el puerto durante los tests.

**Por qué un gestor de contexto y no una fixture asíncrona.** El *lifespan* de
la app abre un ámbito de cancelación de anyio, y pytest-asyncio puede ejecutar
la fixture y el cuerpo del test en tareas distintas: al salir, anyio protesta
con «attempted to exit cancel scope in a different task». Abriéndolo dentro del
propio test, entrada y salida ocurren en la misma tarea.
"""

from contextlib import asynccontextmanager

import httpx
import pytest

from backend.api import catalog
from backend.api.schemas import ServerStatus
from backend.config.settings import settings
from backend.core.mcp import session as mcp_session
from backend.integrations.nlp.model_cards import cards_by_signal

# El Host debe llevar puerto: la protección anti DNS-rebinding de FastMCP acepta
# `127.0.0.1:*` y rechazaría con 421 un Host sin él.
_BASE = "http://127.0.0.1:8765"
_URL = f"{_BASE}/mcp"


@asynccontextmanager
async def servidor_en_proceso(monkeypatch, mcp):
    """Hace que el catálogo hable con la app MCP sin salir del proceso."""
    app = mcp.streamable_http_app()

    # El gestor de sesiones de FastMCP arranca en el lifespan de la app, y
    # ASGITransport no lo ejecuta: hay que entrarlo a mano o toda petición falla.
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


async def _catalogo(monkeypatch, mcp):
    """Atajo: levanta el servidor en proceso y devuelve el catálogo."""
    async with servidor_en_proceso(monkeypatch, mcp):
        return await catalog.fetch_catalog()


async def _tools(monkeypatch, mcp):
    return {t.name: t for t in (await _catalogo(monkeypatch, mcp)).tools}


# ----- Descubrimiento -----


@pytest.mark.asyncio
async def test_el_catalogo_se_construye_por_handshake(monkeypatch, servidor_mcp):
    resultado = await _catalogo(monkeypatch, servidor_mcp)

    assert len(resultado.servers) == 1
    servidor = resultado.servers[0]
    assert servidor.status == ServerStatus.OK
    # El nombre lo declara el propio servidor en el handshake, no la config.
    assert servidor.name == "tfg-mcp-server"
    assert servidor.tool_count == len(resultado.tools) == 11
    assert not resultado.degraded


@pytest.mark.asyncio
async def test_cada_tool_trae_nombre_descripcion_y_esquema(monkeypatch, servidor_mcp):
    # El esquema de parámetros viaja crudo, con sus restricciones.
    tools = await _tools(monkeypatch, servidor_mcp)

    lexical = tools["detect_clickbait_lexical"]
    assert lexical.description
    assert "headline" in lexical.input_schema["properties"]
    assert lexical.server == "tfg-mcp-server"


# ----- Categoría y procedencia  -----


@pytest.mark.asyncio
async def test_las_tools_declaran_categoria_y_procedencia(monkeypatch, servidor_mcp):
    tools = await _tools(monkeypatch, servidor_mcp)

    assert tools["get_nyt_news"].category == "Fuentes de contenido"
    assert tools["get_nyt_news"].integration == "nyt"
    assert tools["detect_clickbait_lexical"].category == "Señales de análisis"
    assert tools["detect_clickbait_lexical"].integration == "nlp"


@pytest.mark.asyncio
async def test_la_categoria_no_se_deriva_del_paquete(monkeypatch, servidor_mcp):
    # `describe_models` vive en nlp/ pero es una utilidad: describe modelos, no
    # analiza nada. Es el caso que obliga a declarar la categoría a mano.
    tools = await _tools(monkeypatch, servidor_mcp)

    assert tools["describe_models"].integration == "nlp"
    assert tools["describe_models"].category == "Utilidades"


@pytest.mark.asyncio
async def test_una_tool_del_nucleo_no_tiene_integracion(monkeypatch, servidor_mcp):
    # health_check vive en core/ y no envuelve ninguna fuente externa.
    tools = await _tools(monkeypatch, servidor_mcp)

    assert tools["health_check"].category == "Utilidades"
    assert tools["health_check"].integration is None


# ----- Fichas de modelo -----


@pytest.mark.asyncio
async def test_las_senales_traen_su_ficha_de_modelo(monkeypatch, servidor_mcp):
    tools = await _tools(monkeypatch, servidor_mcp)

    fichas = cards_by_signal()

    ficha = tools["detect_clickbait_lexical"].model_card
    assert ficha is not None
    assert ficha.type.value == "interpretable"
    assert ficha.dimension.value == "form"
    # Los límites medidos son lo que evita que el catálogo prometa de más.
    assert any("0.498" in limite for limite in ficha.limitations)

    # El nombre y la tarea viajan desde #128, y se comparan contra la ficha en
    # vez de contra una cadena escrita aquí: así renombrar una señal en
    # `model_cards.py` no puede desalinear el test de lo que se publica.
    assert ficha.name == fichas["detect_clickbait_lexical"]["name"]
    assert ficha.task == fichas["detect_clickbait_lexical"]["task"]
    # Sin ellos la pantalla sólo podía titular «detect_clickbait_lexical», que es
    # justo lo que `ToolModelCard` dice en su docstring que quiere evitar.
    assert "detect_clickbait_lexical" not in ficha.name


@pytest.mark.asyncio
async def test_un_model_id_nulo_es_informacion_y_viaja(monkeypatch, servidor_mcp):
    """`model_id` es `None` en el léxico y el lineal, y ese None se publica.

    Dice que la señal NO es un modelo descargable sino código propio y
    auditable, que bajo R3.9 es más divulgador que esconderlo. El dedicado sí
    trae su identificador de HuggingFace.
    """
    tools = await _tools(monkeypatch, servidor_mcp)

    lexico = tools["detect_clickbait_lexical"].model_card
    dedicado = tools["detect_clickbait"].model_card
    assert lexico is not None and dedicado is not None

    assert lexico.model_id is None
    assert dedicado.model_id == cards_by_signal()["detect_clickbait"]["model_id"]


@pytest.mark.asyncio
async def test_solo_las_senales_traen_ficha(monkeypatch, servidor_mcp):
    tools = await _tools(monkeypatch, servidor_mcp)

    con_ficha = {n for n, t in tools.items() if t.model_card is not None}
    senales = {n for n, t in tools.items() if t.category == "Señales de análisis"}

    # La categoría predice si hay ficha: no es casualidad, es el criterio.
    assert con_ficha == senales


# ----- Degradación  -----


@pytest.mark.asyncio
async def test_sin_servidores_configurados_no_es_degradacion(monkeypatch):
    """Cero servidores da catálogo vacío pero NO degradado, y es lo correcto.

    `gather()` sin corrutinas devuelve `[]`, el bucle no se ejecuta y `any([])`
    es False. Pero lo que importa es la semántica: `degraded` significa «algo
    declarado no responde», y sin nada declarado no ha fallado nada. Esto es una
    **mala configuración**, no una degradación.

    La distinción vale la pena porque el contrato permite separar las dos formas
    de acabar sin herramientas: `servers` vacío es que no hay nada configurado;
    `servers` con entradas `unreachable` es que está declarado y no responde. Si
    la lista vacía marcara `degraded`, ambas colapsarían en una y la interfaz no
    podría decir cuál de las dos está pasando.
    """
    monkeypatch.setattr(settings, "mcp_servers", [])

    resultado = await catalog.fetch_catalog()

    assert resultado.servers == []
    assert resultado.tools == []
    assert not resultado.degraded


@pytest.mark.asyncio
async def test_un_servidor_caido_no_rompe_la_respuesta(monkeypatch, servidor_mcp):
    monkeypatch.setattr(settings, "mcp_servers", ["http://127.0.0.1:1/mcp"])
    monkeypatch.setattr(settings, "mcp_timeout", 1.0)

    resultado = await catalog.fetch_catalog()

    assert resultado.degraded
    servidor = resultado.servers[0]
    assert servidor.status == ServerStatus.UNREACHABLE
    assert servidor.detail  # el motivo, para poder diagnosticarlo
    assert servidor.tool_count == 0
    # Lo importante: hay respuesta, no una excepción.
    assert resultado.tools == []
