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
            "instruction": "Move to higher ground immediately",
        }
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
async def test_alert_exists(fake_alert):
    with respx.mock:
        respx.get("https://api.weather.gov/alerts/active/area/CA").mock(
            return_value=Response(200, json={"features": [fake_alert]})
        )

        api = WeatherAPI()
        result = await api.get_alerts_API("CA")

        assert result.success
        assert "Flood Warning" in result.data


@pytest.mark.asyncio
async def test_alerts_empty_features():
    with respx.mock:
        respx.get("https://api.weather.gov/alerts/active/area/CA").mock(
            return_value=Response(200, json={"features": []})
        )

        api = WeatherAPI()
        result = await api.get_alerts_API("CA")

        assert "No active alerts for this state." in result.data


@pytest.mark.asyncio
async def test_alerts_bad_response():
    with respx.mock:
        respx.get("https://api.weather.gov/alerts/active/area/CA").mock(
            return_value=Response(500, json={"features": []})
        )

        api = WeatherAPI()
        result = await api.get_alerts_API("CA")
        # print()
        # print(result.error)
        assert not result.success
        assert "500" in result.error


@pytest.mark.asyncio
async def test_get_forecast(fake_forecast_periods):
    with respx.mock:
        respx.get("https://api.weather.gov/points/40.7128,-74.006").mock(
            return_value=Response(
                200,
                json={
                    "properties": {
                        "forecast": "https://api.weather.gov/gridpoints/OKX/33,42/forecast",
                    }
                },
            )
        )

        respx.get("https://api.weather.gov/gridpoints/OKX/33,42/forecast").mock(
            return_value=Response(
                200, json={"properties": {"periods": fake_forecast_periods}}
            )
        )

        api = WeatherAPI()
        zone_url = await api.get_zone_by_points(40.7128, -74.006)

        print(zone_url)
        response = await api.get_forecast_API(zone_url.data)

        assert zone_url.success
        assert "gridpoints" in zone_url.data

        assert response.success
        assert response.data is not None
        assert "periods" in response.data.get("properties", {})
