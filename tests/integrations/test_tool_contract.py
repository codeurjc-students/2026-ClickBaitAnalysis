"""Tests del contrato de retorno de las tools MCP.

Este fichero cubre un hueco que se destapó al cambiar el contrato: los tests
existentes prueban la **capa cliente** (`lexical.detect`, `HFClient`…), que
devuelve `ToolResult`, pero nadie comprobaba cómo traduce eso la tool al
protocolo. Por eso el cambio de «devolver el error» a «lanzarlo» pasó sin que
fallara un solo test.

Se habla el protocolo real contra la app en el mismo proceso, con
`ASGITransport`. Se usan sólo tools locales y deterministas: nada de red.
"""

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
        "matches",
        "headline",
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
