import pytest

from backend.core.health import _aggregate_status, _probe_guardian, _probe_weather


def test_aggregate_status_all_ok():
    integrations = {
        "weather": {"reachable": True, "error": None},
        "guardian": {"reachable": True, "error": None},
    }
    assert _aggregate_status(integrations) == "ok"


def test_aggregate_status_one_fails():
    integrations = {
        "weather": {"reachable": True, "error": None},
        "guardian": {"reachable": False, "error": "boom"},
    }
    assert _aggregate_status(integrations) == "degraded"


def test_aggregate_status_all_fail():
    integrations = {
        "weather": {"reachable": False, "error": "boom"},
        "guardian": {"reachable": False, "error": "boom"},
    }
    assert _aggregate_status(integrations) == "down"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_probe_weather_reaches_api():
    result = await _probe_weather()
    assert result["reachable"] is True
    assert result["error"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_probe_guardian_reaches_api():
    result = await _probe_guardian()
    assert result["reachable"] is True
    assert result["error"] is None
