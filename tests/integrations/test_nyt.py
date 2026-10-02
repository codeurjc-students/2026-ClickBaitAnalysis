import pytest
import respx
from httpx import Response
from mcp.server.fastmcp import FastMCP

from backend.core.models import ToolResult
from backend.integrations.nyt import tool as nyt_tool
from backend.integrations.nyt.client import NYTAPI


@pytest.fixture
def fake_payload():
    return {
        "headline": {
            "main": "Want to ‘Optimize’ Your Happiness? This Happiness Expert Says: Don’t.",
            "print_headline": "The Happiness Expert",
        },
        "web_url": "https://www.nytimes.com/2026/05/30/magazine/laurie-santos-interview.html",
        "pub_date": "2026-03-10T19:03:21Z",
        "abstract": "A happiness expert on why optimizing happiness backfires.",
    }


@pytest.mark.asyncio
async def test_search_articles_valid_response(fake_payload):

    with respx.mock:
        respx.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(200, json={"response": {"docs": [fake_payload]}})
        )

        api = NYTAPI()
        result = await api.search_articles("hapiness")

        assert result.success
        assert len(result.data) == 1
        assert result.data[0]["title"] == fake_payload["headline"]["main"]
        assert result.data[0]["url"] == fake_payload["web_url"]
        assert result.data[0]["date"] == fake_payload["pub_date"]
        assert result.data[0]["content"] == fake_payload["abstract"]
        assert (
            result.data[0]["print_headline"]
            == fake_payload["headline"]["print_headline"]
        )


@pytest.mark.asyncio
async def test_search_articles_no_results():
    with respx.mock:
        respx.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(200, json={"response": {"docs": []}})
        )

        api = NYTAPI()
        result = await api.search_articles("anything")

        assert not result.success
        assert "No articles found" in result.error


@pytest.mark.asyncio
async def test_search_articles_missing_docs_key():
    with respx.mock:
        respx.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(200, json={"response": {}})
        )

        api = NYTAPI()
        result = await api.search_articles("anything")

        assert not result.success
        assert "No articles found" in result.error


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", [401, 429, 500])
async def test_un_fallo_de_la_api_no_se_disfraza_de_sin_noticias(estado):
    """#212, lo que #196 arregló en Guardian: con una clave mala, la cuota
    agotada o un error del servidor, el cliente decía «No articles found», y
    el agente, creyéndolo, gastaría cuota probando otros temas. El mensaje de
    `make_request` ya es público (#89): se devuelve ése."""
    with respx.mock:
        respx.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(estado, json={"response": {}})
        )
        api = NYTAPI()
        result = await api.search_articles("anything")

    assert not result.success
    assert "No articles found" not in result.error
    assert str(estado) in result.error


@pytest.mark.asyncio
async def test_el_error_publicado_no_lleva_la_clave_ni_la_url(monkeypatch):
    """El error sale por la tool MCP y por `/tools/.../execute`, así que es una
    salida pública (#163). La clave de NYT va en la URL, y el proveedor puede
    repetirla en su respuesta: no puede salir ni una cosa ni la otra."""
    monkeypatch.setattr(NYTAPI, "API_KEY", "clave-de-prueba-212")
    with respx.mock:
        respx.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(401, text="Invalid ApiKey: clave-de-prueba-212")
        )
        api = NYTAPI()
        result = await api.search_articles("anything")

    assert not result.success
    assert "clave-de-prueba-212" not in result.error
    assert "nytimes.com" not in result.error


@pytest.mark.asyncio
async def test_topic_uses_relevance_sort(fake_payload):
    # Con topic, sort=relevance (el fix del bug) + q=<topic>.
    with respx.mock:
        route = respx.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(200, json={"response": {"docs": [fake_payload]}})
        )
        api = NYTAPI()
        await api.search_articles("artificial intelligence")

    sent = route.calls.last.request.url.params
    assert sent["sort"] == "relevance"
    assert sent["q"] == "artificial intelligence"


@pytest.mark.asyncio
async def test_no_topic_uses_newest_sort(fake_payload):
    # Sin topic, sort=newest (lo más reciente) y sin q.
    with respx.mock:
        route = respx.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(200, json={"response": {"docs": [fake_payload]}})
        )
        api = NYTAPI()
        await api.search_articles()

    sent = route.calls.last.request.url.params
    assert sent["sort"] == "newest"
    assert "q" not in sent


@pytest.mark.asyncio
async def test_tracking_and_derived_quota(fake_payload):
    with respx.mock:
        respx.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(200, json={"response": {"docs": [fake_payload]}})
        )
        api = NYTAPI()
        assert api.remaining_quota is None  # sin llamadas aún

        await api.search_articles("technology")

    assert api.call_count == 1

    # Forzar a declarar Limite en NYTAPI.
    assert NYTAPI.DAILY_LIMIT is not None
    assert api.remaining_quota == NYTAPI.DAILY_LIMIT - api.call_count


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_articles_valid_use():

    api = NYTAPI()
    result = await api.search_articles("technology")

    assert result.success
    # print(result.data)
    assert result.data[0]["title"] is not None
    assert result.data[0]["url"] is not None
    assert result.data[0]["date"] is not None


# WARNING!!!!
# COMPROBAR MANUALMENTE QUE EL TEMA SELECCIONADO NO EXISTE Y NO DEVUELVE RESULTADOS
@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_articles_invalid_topic():

    api = NYTAPI()
    result = await api.search_articles("nonexistingtopicabcde")
    # print(result.data)
    assert not result.success
    assert result.error
    assert "No articles found" in result.error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_una_clave_mala_da_el_error_real(monkeypatch):
    """#212, contra la API real: con una clave que no existe, NYT responde 401
    (medido el 2026-10-02), y eso no es «no hay noticias». La clave tampoco
    puede salir."""
    monkeypatch.setattr(NYTAPI, "API_KEY", "clave-que-no-existe-212")
    api = NYTAPI()
    result = await api.search_articles("technology")

    assert not result.success
    assert "No articles found" not in result.error, result.error
    assert "401" in result.error
    assert "clave-que-no-existe-212" not in result.error


@pytest.mark.asyncio
async def test_un_tema_que_solo_dice_none_es_buscar_sin_tema(monkeypatch):
    """#197: el `topic` es opcional, y el modelo del agente puede escribir su
    ausencia como «None». Buscarlo como tema traería noticias sobre la palabra."""
    recibido = []

    async def buscar(self, topic=None, days=7):
        recibido.append(topic)
        return ToolResult.ok([])

    monkeypatch.setattr(NYTAPI, "search_articles", buscar)
    mcp = FastMCP("test")
    nyt_tool.register(mcp)

    await mcp.call_tool("get_nyt_news", {"topic": "None"})

    assert recibido == [None]
