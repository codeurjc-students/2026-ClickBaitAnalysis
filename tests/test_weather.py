from backend.integrations.weather.client import WeatherAPI
import respx
import pytest
from httpx import Response


@pytest.fixture
def fake_alert():
    return {
        "properties": {
            "event": "Flood Warning",
            "areaDesc": "San Francisco County",
            "severity": "Severe",
            "description": "Flooding expected in low-lying areas",
            "instruction": "Move to higher ground immediately"
        }
    }
@pytest.mark.asyncio
async def test_alert_exists(fake_alert):
    with respx.mock:
        respx.get("https://api.weather.gov/alerts/active/area/CA").mock(
            return_value=Response(200, json={"features": [fake_alert]})
        )
        
        # Llamas a tu código normalmente
        api = WeatherAPI()
        result = await api.get_alerts_API("CA")
        # print(result)
        
        # Verificas
        assert result.success
        assert "Flood Warning" in result.data
