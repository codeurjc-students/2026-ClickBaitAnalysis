import pytest

from backend.core.health import PROBES, _aggregate_status, _probe


def test_aggregate_status_all_ok():
    integrations = {
        "weather": {"reachable": True, "error": None},
        "guardian": {"reachable": True, "error": None},
        "nyt": {"reachable": True, "error": None},
    }
    assert _aggregate_status(integrations) == "ok"


def test_aggregate_status_one_fails():
    integrations = {
        "weather": {"reachable": True, "error": None},
        "guardian": {"reachable": False, "error": "boom"},
        "nyt": {"reachable": True, "error": None},
    }
    assert _aggregate_status(integrations) == "degraded"


def test_aggregate_status_some_fail():
    integrations = {
        "weather": {"reachable": False, "error": "boom"},
        "guardian": {"reachable": False, "error": "boom"},
        "nyt": {"reachable": True, "error": None},
    }
    assert _aggregate_status(integrations) == "degraded"


def test_aggregate_status_all_fail():
    integrations = {
        "weather": {"reachable": False, "error": "boom"},
        "guardian": {"reachable": False, "error": "boom"},
        "nyt": {"reachable": False, "error": "boom"},
    }
    assert _aggregate_status(integrations) == "down"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(PROBES))
async def test_probe_reaches_api(name):
    result = await _probe(**PROBES[name])
    assert result["reachable"] is True
    assert result["error"] is None
