"""Tests del contrato de retorno de las tools MCP.

Este fichero cubre un hueco que se destapó al cambiar el contrato: los tests
existentes prueban la **capa cliente** (`lexical.detect`, `HFClient`…), que
devuelve `ToolResult`, pero nadie comprobaba cómo traduce eso la tool al
protocolo. Por eso el cambio de «devolver el error» a «lanzarlo» pasó sin que
fallara un solo test.

Se habla el protocolo real contra la app en el mismo proceso, con
`ASGITransport`. Se usan sólo tools locales y deterministas: nada de red.
"""

import json
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

_BASE = "http://127.0.0.1:8765"

# Las que devuelven prosa formateada para leer, no datos: su esquema envuelto
# en `result` es correcto, no una carencia.
TOOLS_DE_TEXTO = {"get_alerts", "get_forecast"}


@asynccontextmanager
async def sesion(mcp):
    """Abre una sesión MCP contra la app, sin abrir puertos."""
    app = mcp.streamable_http_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE
        ) as http_client,
        streamable_http_client(f"{_BASE}/mcp", http_client=http_client) as (r, w, _),
        ClientSession(r, w) as s,
    ):
        await s.initialize()
        yield s


@pytest.mark.asyncio
async def test_todas_las_tools_publican_su_esquema_de_salida(servidor_mcp):
    """Sin tipo declarado, MCP no publica `outputSchema` y el consumidor queda a
    ciegas: se comprobó que `-> dict` a secas lo deja en None."""
    async with sesion(servidor_mcp) as s:
        sin_esquema = [
            t.name for t in (await s.list_tools()).tools if not t.outputSchema
        ]

    assert sin_esquema == []


@pytest.mark.asyncio
async def test_las_tools_de_datos_describen_sus_campos(servidor_mcp):
    """Las que devuelven datos declaran sus campos; las de texto los envuelven.

    Un esquema con una sola propiedad `result` significa que la salida no es un
    objeto —una lista o una cadena— y MCP la envuelve. Correcto para las de
    texto; sospechoso para una señal de análisis, que sí tiene estructura.
    """
    async with sesion(servidor_mcp) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}

    lexical = tools["detect_clickbait_lexical"]
    assert set(lexical.outputSchema["properties"]) == {
        "score",
        "is_clickbait",
        "threshold",  # desde #93, como el de la incoherencia
        "matches",
        "headline",
        "language",  # desde #230, en qué idioma se analizó
    }

    # Las de texto sí van envueltas, y es lo esperado.
    for nombre in TOOLS_DE_TEXTO:
        assert list(tools[nombre].outputSchema["properties"]) == ["result"]


@pytest.mark.asyncio
async def test_una_lista_declara_el_tipo_de_sus_elementos(servidor_mcp):
    # Envuelta en `result` por no ser objeto, pero con el esquema del elemento
    # dentro: el consumidor sabe qué campos trae cada artículo.
    async with sesion(servidor_mcp) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}

    esquema = tools["get_nyt_news"].outputSchema
    assert esquema["properties"]["result"]["type"] == "array"
    articulo = esquema["$defs"]["Articulo"]
    assert "print_headline" in articulo["properties"]


@pytest.mark.asyncio
async def test_describe_models_no_publica_las_notas_de_operacion(servidor_mcp):
    """#211: lo que el agente recibe de `describe_models` son los límites de cada
    señal, no cómo se instala o se sirve. Las notas de operación —`torch` y
    `sentence-transformers` fuera de `requirements.txt`, la vía remota que no
    existe— se las repetía a cualquiera que preguntara. Se mira lo que entrega
    el protocolo, en sus dos formas: la estructurada y el texto, que FastMCP
    manda en un bloque por ficha."""
    from backend.integrations.nlp.model_cards import MODEL_CARDS

    notas = {nota for ficha in MODEL_CARDS for nota in ficha["operation"]}
    assert notas  # si no, el test no comprobaría nada

    async with sesion(servidor_mcp) as s:
        resultado = await s.call_tool("describe_models", {})

    assert resultado.isError is False
    fichas = resultado.structuredContent["result"]
    assert fichas == [json.loads(bloque.text) for bloque in resultado.content]
    for ficha in fichas:
        assert "operation" not in ficha, ficha["signal"]
        assert notas.isdisjoint(ficha["limitations"]), ficha["signal"]


@pytest.mark.asyncio
async def test_describe_models_publica_una_ficha_por_idioma(servidor_mcp, monkeypatch):
    """#230: una ficha por cada idioma que analiza cada señal, con la misma
    regla que la puerta. Hoy, todas en inglés, y en español la del lineal
    (bilingüe desde #231) y la de la dedicada (#242); un modelo puesto por
    configuración en español añade la suya, y sólo la suya."""
    from backend.config.settings import settings

    # Una sola sesión: la app sólo se puede arrancar una vez, y la
    # configuración se lee en cada llamada, así que basta cambiarla entre dos.
    async with sesion(servidor_mcp) as s:
        antes = (await s.call_tool("describe_models", {})).structuredContent["result"]
        monkeypatch.setattr(
            settings, "nlp_models_es", {"analyze_sentiment": "prueba/multilingue"}
        )
        despues = (await s.call_tool("describe_models", {})).structuredContent["result"]

    assert {ficha["signal"] for ficha in antes if ficha["language"] == "es"} == {
        "detect_clickbait",
        "detect_clickbait_linear",
    }
    nuevas = [ficha for ficha in despues if ficha not in antes]
    assert [
        (ficha["signal"], ficha["language"], ficha["model_id"]) for ficha in nuevas
    ] == [("analyze_sentiment", "es", "prueba/multilingue")]


# ----- El eje éxito/fallo lo lleva el protocolo -----


@pytest.mark.asyncio
async def test_una_ejecucion_correcta_devuelve_datos_estructurados(servidor_mcp):
    async with sesion(servidor_mcp) as s:
        resultado = await s.call_tool(
            "detect_clickbait_lexical", {"headline": "10 Things You Won't Believe"}
        )

    assert resultado.isError is False
    # Estructurado, no una cadena que haya que parsear.
    assert resultado.structuredContent["is_clickbait"] is True
    assert resultado.structuredContent["matches"]
    # Y dice en qué idioma lo analizó (#230): lo lee el historial.
    assert resultado.structuredContent["language"] == "en"


@pytest.mark.asyncio
async def test_las_herramientas_deciden_con_el_umbral_configurado(
    servidor_mcp, monkeypatch
):
    """#93 por la fachada MCP: el umbral y el tope se piden a la factoría en
    cada llamada, así que cambiarlos después de registrar las herramientas cambia
    lo que devuelven (la trampa de #87). La fachada REST, en `test_nlp.py`."""
    from backend.config.settings import settings

    monkeypatch.setattr(settings, "nlp_thresholds", {"detect_clickbait_lexical": 2})
    monkeypatch.setattr(settings, "nlp_linear_top_cues", 1)

    async with sesion(servidor_mcp) as s:
        lexica = await s.call_tool(
            "detect_clickbait_lexical", {"headline": "Spain wins the World Cup?"}
        )
        lineal = await s.call_tool(
            "detect_clickbait_linear",
            {"headline": "10 amazing things you won't believe"},
        )

    assert lexica.structuredContent["score"] == 1
    assert lexica.structuredContent["is_clickbait"] is False
    assert lexica.structuredContent["threshold"] == 2
    assert len(lineal.structuredContent["top_cues"]) == 1


@pytest.mark.asyncio
async def test_un_fallo_de_la_tool_marca_isError(servidor_mcp):
    """El caso que motivó el cambio.

    Antes, un titular vacío devolvía el mensaje de error por el mismo canal que
    un resultado válido, con `isError` a False: desde fuera era indistinguible
    de un éxito. Ahora la tool lanza y el protocolo lo marca.
    """
    async with sesion(servidor_mcp) as s:
        resultado = await s.call_tool("detect_clickbait_lexical", {"headline": "   "})

    assert resultado.isError is True
    assert resultado.structuredContent is None
    # El motivo sigue siendo legible para quien lo reciba.
    assert "vacío" in resultado.content[0].text


@pytest.mark.asyncio
async def test_un_parametro_invalido_tambien_marca_isError(servidor_mcp):
    # Este ya funcionaba: lo valida la capa MCP antes de llegar a la tool.
    async with sesion(servidor_mcp) as s:
        resultado = await s.call_tool("detect_clickbait_lexical", {"mal": "parametro"})

    assert resultado.isError is True
