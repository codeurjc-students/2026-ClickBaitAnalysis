from datetime import date, timedelta

from backend.integrations.guardian.client import GuardianAPI
import respx
import pytest
from httpx import Response

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
    }


@pytest.fixture
def fake_forecast_periods():
    return [
        {
            "number": 1,
            "name": "This Afternoon",
            "startTime": "2026-05-21T12:00:00-04:00",
            "endTime": "2026-05-21T18:00:00-04:00",
            "isDaytime": True,
            "temperature": 63,
            "temperatureUnit": "F",
            "temperatureTrend": None,
            "probabilityOfPrecipitation": {
                "unitCode": "wmoUnit:percent",
                "value": 92,
            },
            "windSpeed": "7 to 10 mph",
            "windDirection": "NE",
            "icon": "https://api.weather.gov/icons/land/day/rain,90?size=medium",
            "shortForecast": "Light Rain",
            "detailedForecast": "Rain. Cloudy, with a high near 63. Northeast wind 7 to 10 mph. Chance of precipitation is 90%. New rainfall amounts between a tenth and quarter of an inch possible.",
        },
        {
            "number": 2,
            "name": "Tonight",
            "startTime": "2026-05-21T18:00:00-04:00",
            "endTime": "2026-05-22T06:00:00-04:00",
            "isDaytime": False,
            "temperature": 54,
            "temperatureUnit": "F",
            "temperatureTrend": None,
            "probabilityOfPrecipitation": {
                "unitCode": "wmoUnit:percent",
                "value": 27,
            },
            "windSpeed": "2 to 9 mph",
            "windDirection": "E",
            "icon": "https://api.weather.gov/icons/land/night/rain,30/bkn?size=medium",
            "shortForecast": "Chance Light Rain then Mostly Cloudy",
            "detailedForecast": "A chance of rain before 8pm. Mostly cloudy. Low around 54, with temperatures rising to around 57 overnight. East wind 2 to 9 mph. Chance of precipitation is 30%.",
        },
    ]


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
