import pytest
import respx
from httpx import Response

from backend.integrations.news.client import GuardianAPI


@pytest.fixture
def fake_guardian_article():
    return {
        "webTitle": "‘We’re expanding the cinematic toolbox’: AI fault lines on show at Cannes",
        "webUrl": "https://www.theguardian.com/technology/2026/may/24/cinematic-toolbox-ai-fault-lines-cannes",
        "webPublicationDate": "2026-05-24T05:00:48Z",
    }


@pytest.mark.asyncio
async def test_news_valid_response(fake_guardian_article):
    with respx.mock:
        respx.get("https://content.guardianapis.com/search").mock(
            return_value=Response(
                200,
                json={"response": {"results": [fake_guardian_article]}},
            )
        )

        api = GuardianAPI()
        result = await api.get_news_this_week_call("technology")

        assert result.success
        assert len(result.data) == 1
        assert result.data[0]["title"] == fake_guardian_article["webTitle"]
        assert result.data[0]["url"] == fake_guardian_article["webUrl"]
        assert result.data[0]["date"] == fake_guardian_article["webPublicationDate"]


@pytest.mark.asyncio
async def test_news_missing_results_field():
    """Bug fix #14: payload sin 'results' no debe lanzar TypeError."""
    with respx.mock:
        respx.get("https://content.guardianapis.com/search").mock(
            return_value=Response(200, json={"response": {}})
        )

        api = GuardianAPI()
        result = await api.get_news_this_week_call("technology")

        assert not result.success
        assert "No articles found" in result.error


@pytest.mark.asyncio
async def test_news_empty_results():
    """Lista vacía se trata igual que ausencia de campo (mismo guard)."""
    with respx.mock:
        respx.get("https://content.guardianapis.com/search").mock(
            return_value=Response(200, json={"response": {"results": []}})
        )

        api = GuardianAPI()
        result = await api.get_news_this_week_call("technology")

        assert not result.success
        assert "No articles found" in result.error
