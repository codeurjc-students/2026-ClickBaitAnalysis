from datetime import date, timedelta

import pytest
import respx
from httpx import Response
from mcp.server.fastmcp import FastMCP

from backend.core.models import ToolResult
from backend.integrations.guardian import tool as guardian_tool
from backend.integrations.guardian.client import GuardianAPI

TAGS_URL = "https://content.guardianapis.com/tags"
SEARCH_URL = "https://content.guardianapis.com/search"


def _mock_tags(tag_id="technology/test"):
    """Mockea /tags: devuelve un tag (o ninguno si tag_id=None), para controlar
    la rama tag vs fallback a `q` de search_articles."""
    results = [{"id": tag_id}] if tag_id else []
    respx.get(TAGS_URL).mock(
        return_value=Response(200, json={"response": {"results": results}})
    )


@pytest.fixture
def fake_payload():
    return {
        "webTitle": "‘We’re expanding the cinematic toolbox’: AI fault lines on show at Cannes",
        "webUrl": "https://www.theguardian.com/technology/2026/may/24/cinematic-toolbox-ai-fault-lines-cannes",
        "webPublicationDate": "2026-05-24T05:00:48Z",
        "fields": {"trailText": "AI fault lines on show at Cannes"},
    }


@pytest.mark.asyncio
async def test_article_valid_response(fake_payload):

    with respx.mock:
        _mock_tags()
        respx.get("https://content.guardianapis.com/search").mock(
            return_value=Response(200, json={"response": {"results": [fake_payload]}})
        )

        api = GuardianAPI()
        result = await api.search_articles("technology")

        assert result.success
        assert len(result.data) == 1
        assert result.success
        assert len(result.data) == 1
        assert result.data[0]["title"] == fake_payload["webTitle"]
        assert result.data[0]["url"] == fake_payload["webUrl"]
        assert result.data[0]["date"] == fake_payload["webPublicationDate"]
        assert result.data[0]["content"] == fake_payload["fields"]["trailText"]


@pytest.mark.asyncio
async def test_article_no_results():
    with respx.mock:
        _mock_tags()
        respx.get("https://content.guardianapis.com/search").mock(
            return_value=Response(200, json={"response": {"results": []}})
        )

        api = GuardianAPI()
        result = await api.search_articles("asdfghjkl")

        assert not result.success
        assert "No articles found" in result.error


@pytest.mark.asyncio
async def test_article_missing_results_key():
    with respx.mock:
        _mock_tags()
        respx.get("https://content.guardianapis.com/search").mock(
            return_value=Response(200, json={"response": {}})
        )

        api = GuardianAPI()
        result = await api.search_articles("anything")

        assert not result.success
        assert "No articles found" in result.error


@pytest.mark.asyncio
async def test_topic_uses_tag(fake_payload):
    # Con tag, búsqueda usa tag=<id> y NO q.
    with respx.mock:
        _mock_tags("technology/artificialintelligenceai")
        search = respx.get(SEARCH_URL).mock(
            return_value=Response(200, json={"response": {"results": [fake_payload]}})
        )
        api = GuardianAPI()
        result = await api.search_articles("artificial intelligence")

    assert result.success
    sent = search.calls.last.request.url.params
    assert sent["tag"] == "technology/artificialintelligenceai"
    assert "q" not in sent


@pytest.mark.asyncio
async def test_no_tag_falls_back_to_q(fake_payload):
    # Sin tag, fallback q=<topic>.
    with respx.mock:
        _mock_tags(None)
        search = respx.get(SEARCH_URL).mock(
            return_value=Response(200, json={"response": {"results": [fake_payload]}})
        )
        api = GuardianAPI()
        result = await api.search_articles("tema-raro")

    assert result.success
    sent = search.calls.last.request.url.params
    assert sent["q"] == "tema-raro"
    assert "tag" not in sent


@pytest.mark.asyncio
async def test_una_etiqueta_sin_noticias_vuelve_a_la_busqueda_libre(fake_payload):
    """#196: `_find_tag` elige a veces una etiqueta muerta —una serie cerrada,
    una sección sin nada en la semana— y la búsqueda se quedaba en «No articles
    found» aunque `q=` trajera noticias (medido: 5 de 8 temas)."""

    def por_parametros(request):
        if "tag" in request.url.params:
            return Response(200, json={"response": {"results": []}})
        return Response(200, json={"response": {"results": [fake_payload]}})

    with respx.mock:
        _mock_tags("climate-summit/climate-summit")
        search = respx.get(SEARCH_URL).mock(side_effect=por_parametros)
        api = GuardianAPI()
        result = await api.search_articles("climate")

    assert result.success
    assert result.data[0]["title"] == fake_payload["webTitle"]
    primera, segunda = (llamada.request.url.params for llamada in search.calls)
    assert primera["tag"] == "climate-summit/climate-summit"
    assert segunda["q"] == "climate"
    assert "tag" not in segunda
    assert segunda["from-date"] == primera["from-date"]


@pytest.mark.asyncio
async def test_un_fallo_de_la_api_no_se_disfraza_de_sin_noticias():
    """#196: con un 429 —o un 401, o un timeout— el cliente decía «No articles
    found», y el agente, creyéndolo, gastaría cuota probando otros temas. El
    mensaje de `make_request` ya es público (#89): se devuelve ése."""
    with respx.mock:
        _mock_tags("climate/climate")
        search = respx.get(SEARCH_URL).mock(return_value=Response(429))
        api = GuardianAPI()
        result = await api.search_articles("climate")

    assert not result.success
    assert "No articles found" not in result.error
    assert "429" in result.error
    assert search.call_count == 1  # un fallo no se repite con `q=`


@pytest.mark.asyncio
async def test_tracking_and_quota_from_header(fake_payload):
    with respx.mock:
        _mock_tags("technology/test")
        respx.get(SEARCH_URL).mock(
            return_value=Response(
                200,
                json={"response": {"results": [fake_payload]}},
                headers={"x-ratelimit-remaining-day": "42"},
            )
        )
        api = GuardianAPI()
        await api.search_articles("technology")

    assert api.call_count == 2
    assert api.remaining_quota == 42


@pytest.mark.asyncio
async def test_find_tag_prefers_canonical_section(fake_payload):
    # Encuentra el tag canónico
    with respx.mock:
        respx.get(TAGS_URL).mock(
            return_value=Response(
                200,
                json={
                    "response": {
                        "results": [
                            {"id": "sustainable-business/technology"},
                            {"id": "society-professionals/technology"},
                            {"id": "technology/technology"},
                        ]
                    }
                },
            )
        )
        search = respx.get(SEARCH_URL).mock(
            return_value=Response(200, json={"response": {"results": [fake_payload]}})
        )
        api = GuardianAPI()
        await api.search_articles("technology")

    sent = search.calls.last.request.url.params
    # Search = route de respx
    #   -> .calls = lista de llamadas a esa ruta
    #   -> .last = última llamada (hicimos dos)
    #   -> .request = objeto request de esa llamada (no response)
    #   -> .url = URL completo de esa request
    #   -> .params = parámetros de query string enviados en esa request parseados como dict (no string)
    assert sent["tag"] == "technology/technology"


@pytest.mark.asyncio
async def test_find_tag_falls_back_to_first_when_no_canonical(fake_payload):
    # Sin tag canónico X/X = tags[0].
    with respx.mock:
        respx.get(TAGS_URL).mock(
            return_value=Response(
                200,
                json={
                    "response": {
                        "results": [
                            {"id": "technology/artificialintelligenceai"},
                            {"id": "world/ai"},
                        ]
                    }
                },
            )
        )
        search = respx.get(SEARCH_URL).mock(
            return_value=Response(200, json={"response": {"results": [fake_payload]}})
        )
        api = GuardianAPI()
        await api.search_articles("artificial intelligence")

    sent = search.calls.last.request.url.params
    assert sent["tag"] == "technology/artificialintelligenceai"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_news_real_schema_contract():

    api = GuardianAPI()
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
async def test_get_news_invalid_topic():

    api = GuardianAPI()
    result = await api.search_articles("nonexistingtopicabcde")
    # print(result.data)
    assert not result.success
    assert result.error
    assert "No articles found" in result.error


@pytest.mark.asyncio
async def test_un_tema_que_solo_dice_none_es_buscar_sin_tema(monkeypatch):
    """#197: el `topic` es opcional, y el modelo del agente puede escribir su
    ausencia como «None». Buscarlo como tema traería noticias sobre la palabra."""
    recibido = []

    async def buscar(self, topic=None, days=7):
        recibido.append(topic)
        return ToolResult.ok([])

    monkeypatch.setattr(GuardianAPI, "search_articles", buscar)
    mcp = FastMCP("test")
    guardian_tool.register(mcp)

    await mcp.call_tool("get_guardian_news", {"topic": "None"})

    assert recibido == [None]
