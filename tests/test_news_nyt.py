from backend.integrations.nyt.client import NYTAPI
import respx
import pytest
from httpx import Response


@pytest.fixture
def fake_payload():
    return {
        "headline": {
            "main": "Want to ‘Optimize’ Your Happiness? This Happiness Expert Says: Don’t."
        },
        "web_url": "https://www.nytimes.com/2026/05/30/magazine/laurie-santos-interview.html",
        "pub_date": "2026-03-10T19:03:21Z",
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
async def test_search_articles_http_error():
    with respx.mock:
        respx.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(500, json={"response": {}})
        )

        api = NYTAPI()
        result = await api.search_articles("anything")

        assert not result.success
        assert "No articles found" in result.error


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
