"""Tests del cliente y la herramienta de GNews (#235).

Sin red: `respx` hace de GNews, con respuestas de la forma medida en
`spikes/noticias_es.py`. La clave es de prueba (`con_clave`): en el CI no hay
`GNEWS_API_KEY`, y sin ella el cliente no pide nada, que es lo que comprueba
otro test. Los `integration` van contra la API real.
"""

from datetime import UTC, datetime, timedelta

import pytest
import respx
from httpx import Response
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from structlog.testing import capture_logs

from backend.core.models import ToolResult
from backend.integrations.gnews import tool as gnews_tool
from backend.integrations.gnews.client import SIN_CLAVE, GNewsAPI

CLAVE_DE_PRUEBA = "clave-gnews-de-prueba-235"
BUSCAR = f"{GNewsAPI.BASE_URL}search"
DESTACADOS = f"{GNewsAPI.BASE_URL}top-headlines"


def noticia(titulo: str | None = "La IA resolvió el misterio del huevo") -> dict:
    """Una noticia con la forma que devuelve GNews (medida el 9 oct 2026)."""
    return {
        "id": "a1b2c3",
        "title": titulo,
        "description": "Un equipo de investigadores usó un modelo para responder.",
        "content": "Un equipo de investigadores usó un modelo... [2345 chars]",
        "url": "https://www.ejemplo.com/ciencia/huevo-gallina",
        "image": "https://www.ejemplo.com/huevo.jpg",
        "publishedAt": "2026-10-08T19:50:30Z",
        "lang": "es",
        "source": {
            "id": "s1",
            "name": "El Diario",
            "url": "https://www.ejemplo.com",
            "country": "es",
        },
    }


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setattr(GNewsAPI, "API_KEY", CLAVE_DE_PRUEBA)


@pytest.mark.asyncio
async def test_extrae_los_campos_y_el_cuerpo_sale_de_la_entradilla(con_clave):
    """El `content` del plan gratuito llega recortado, con una marca de lo que
    falta: el cuerpo que se devuelve es `description`, entera."""
    esperada = noticia()
    with respx.mock:
        respx.get(BUSCAR).mock(
            return_value=Response(
                200, json={"totalArticles": 1, "articles": [esperada]}
            )
        )
        result = await GNewsAPI().search_articles("inteligencia artificial")

    assert result.success
    assert len(result.data) == 1
    assert result.data[0]["title"] == esperada["title"]
    assert result.data[0]["url"] == esperada["url"]
    assert result.data[0]["date"] == esperada["publishedAt"]
    assert result.data[0]["content"] == esperada["description"]
    assert result.data[0]["source"] == esperada["source"]["name"]


@pytest.mark.asyncio
async def test_con_tema_busca_en_search_en_espanol(con_clave):
    with respx.mock:
        ruta = respx.get(BUSCAR).mock(
            return_value=Response(200, json={"articles": [noticia()]})
        )
        await GNewsAPI().search_articles("inteligencia artificial")

    enviado = ruta.calls.last.request.url.params
    assert enviado["q"] == "inteligencia artificial"
    assert enviado["lang"] == "es"
    assert enviado["max"] == "10"
    assert enviado["apikey"] == CLAVE_DE_PRUEBA
    # Noticias en español, no de un país.
    assert "country" not in enviado


@pytest.mark.asyncio
async def test_sin_tema_pide_los_titulares_destacados(con_clave):
    """`/search` exige `q`: sin tema, `/top-headlines`."""
    with respx.mock:
        ruta = respx.get(DESTACADOS).mock(
            return_value=Response(200, json={"articles": [noticia()]})
        )
        result = await GNewsAPI().search_articles()

    assert result.success
    enviado = ruta.calls.last.request.url.params
    assert "q" not in enviado
    assert enviado["lang"] == "es"


@pytest.mark.asyncio
@pytest.mark.parametrize("dias", [1, 30])
async def test_los_dias_fijan_desde_cuando_en_utc(con_clave, dias):
    with respx.mock:
        ruta = respx.get(BUSCAR).mock(
            return_value=Response(200, json={"articles": [noticia()]})
        )
        await GNewsAPI().search_articles("elecciones", days=dias)

    desde = datetime.strptime(
        ruta.calls.last.request.url.params["from"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=UTC)
    esperado = datetime.now(UTC) - timedelta(days=dias)
    assert abs(desde - esperado) < timedelta(minutes=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cuerpo", [{"totalArticles": 0, "articles": []}, {"totalArticles": 0}]
)
async def test_sin_noticias(con_clave, cuerpo):
    with respx.mock:
        respx.get(BUSCAR).mock(return_value=Response(200, json=cuerpo))
        result = await GNewsAPI().search_articles("nadaquecoincidaabcde")

    assert not result.success
    assert result.error == "No articles found"


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", [400, 401, 403, 429, 500])
async def test_un_fallo_de_la_api_no_se_disfraza_de_sin_noticias(con_clave, estado):
    """Como NYT (#212) y Guardian (#196): creyendo que no hay noticias, el
    agente gastaría cuota probando otros temas. 400 es lo que GNews responde a
    una clave que no existe (medido); 403, según su documentación, la cuota del
    día agotada; 429, más de una petición por segundo."""
    with respx.mock:
        respx.get(BUSCAR).mock(return_value=Response(estado, json={"errors": ["x"]}))
        result = await GNewsAPI().search_articles("elecciones")

    assert not result.success
    assert "No articles found" not in result.error
    assert str(estado) in result.error


@pytest.mark.asyncio
async def test_el_error_publicado_no_lleva_la_clave_ni_la_url(con_clave):
    """El error es una salida pública (#163). La clave va en la URL, y el
    proveedor podría repetirla en su respuesta."""
    with respx.mock:
        respx.get(BUSCAR).mock(
            return_value=Response(400, text=f"Invalid key: {CLAVE_DE_PRUEBA}")
        )
        result = await GNewsAPI().search_articles("elecciones")

    assert not result.success
    assert CLAVE_DE_PRUEBA not in result.error
    assert "gnews.io" not in result.error


@pytest.mark.asyncio
async def test_sin_clave_no_pide_nada_y_dice_que_falta(monkeypatch):
    """La clave es opcional (`settings.gnews_api_key`): sin ella el sistema
    arranca, y esta herramienta dice qué falta sin gastar una petición."""
    monkeypatch.setattr(GNewsAPI, "API_KEY", None)
    with respx.mock(assert_all_called=False):
        ruta = respx.get(BUSCAR)
        result = await GNewsAPI().search_articles("elecciones")

    assert not ruta.called
    assert not result.success
    assert result.error == SIN_CLAVE
    assert "GNEWS_API_KEY" in result.error


@pytest.mark.asyncio
async def test_quita_los_titulares_repetidos(con_clave):
    """La misma noticia llega a veces dos veces (medido): se queda la primera.
    Las que no traen titular no se comparan, y se quedan todas."""
    repetida = noticia("Trump no pondrá freno a la IA")
    otra = noticia("Quién gana cuando los dueños de la IA piden regularla")
    sin_titular = noticia(None)
    with respx.mock:
        respx.get(BUSCAR).mock(
            return_value=Response(
                200,
                json={"articles": [repetida, otra, repetida, sin_titular, sin_titular]},
            )
        )
        result = await GNewsAPI().search_articles("inteligencia artificial")

    assert [articulo["title"] for articulo in result.data] == [
        "Trump no pondrá freno a la IA",
        "Quién gana cuando los dueños de la IA piden regularla",
        None,
        None,
    ]


@pytest.mark.asyncio
async def test_la_cuota_restante_es_la_que_cuenta_el_proceso(con_clave):
    """GNews no publica la cuota en ninguna cabecera (medido)."""
    with respx.mock:
        respx.get(BUSCAR).mock(
            return_value=Response(200, json={"articles": [noticia()]})
        )
        api = GNewsAPI()
        assert api.remaining_quota is None  # sin llamadas aún

        await api.search_articles("elecciones")

    assert api.call_count == 1
    assert api.remaining_quota == GNewsAPI.DAILY_LIMIT - 1


@pytest.mark.asyncio
async def test_un_tema_que_solo_dice_none_es_buscar_sin_tema(monkeypatch):
    """#197, como en NYT y Guardian: el modelo del agente puede escribir la
    ausencia del tema como «None»."""
    recibido = []

    async def buscar(self, topic=None, days=7):
        recibido.append(topic)
        return ToolResult.ok([])

    monkeypatch.setattr(GNewsAPI, "search_articles", buscar)
    mcp = FastMCP("test")
    gnews_tool.register(mcp)

    await mcp.call_tool("get_gnews_news", {"topic": "None"})

    assert recibido == [None]


@pytest.mark.asyncio
async def test_la_herramienta_sin_clave_dice_que_falta(monkeypatch):
    monkeypatch.setattr(GNewsAPI, "API_KEY", None)
    mcp = FastMCP("test")
    gnews_tool.register(mcp)

    # `capture_logs`: el decorador de la herramienta registra el fallo con su
    # traza, y con la configuración de structlog por defecto eso avisa.
    with capture_logs(), pytest.raises(ToolError, match="GNEWS_API_KEY"):
        await mcp.call_tool("get_gnews_news", {"topic": "elecciones"})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_una_clave_mala_da_el_error_real(monkeypatch):
    """Contra la API real: a una clave que no existe GNews responde 400, como si
    faltara (medido el 9 oct 2026), y eso no es «no hay noticias». La clave
    tampoco puede salir."""
    monkeypatch.setattr(GNewsAPI, "API_KEY", "clave-que-no-existe-235")
    result = await GNewsAPI().search_articles("elecciones")

    assert not result.success
    assert "No articles found" not in result.error, result.error
    assert "400" in result.error
    assert "clave-que-no-existe-235" not in result.error


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(GNewsAPI.API_KEY is None, reason="sin GNEWS_API_KEY")
async def test_trae_noticias_en_espanol():
    """Gasta una de las 100 peticiones del día."""
    result = await GNewsAPI().search_articles("inteligencia artificial")

    assert result.success, result.error
    assert result.data[0]["title"]
    assert result.data[0]["url"]
    assert result.data[0]["content"]
