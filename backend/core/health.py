import asyncio
from datetime import datetime, timezone
from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP

from backend.config.settings import settings
from backend.core.observability import log_tool_invocation

PROBE_TIMEOUT = 5


async def _probe_weather() -> dict:
    """Probe weather.gov homepage (no auth required)."""
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            response = await client.get("https://api.weather.gov/")
            response.raise_for_status()  # EVita que se trate 500 como respuesta aceptable
        return {"reachable": True, "error": None}
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": str(exc)}


async def _probe_guardian() -> dict:
    """Probe Guardian search endpoint with the configured API key."""
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            response = await client.get(
                "https://content.guardianapis.com/search",
                params={"page-size": 1, "api-key": settings.guardian_api_key},
            )
            response.raise_for_status()
        return {"reachable": True, "error": None}
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": str(exc)}


def _aggregate_status(integrations: dict) -> Literal["ok", "degraded", "down"]:
    reachable = sum(1 for i in integrations.values() if i["reachable"])
    total = len(integrations)
    if reachable == total:
        return "ok"
    if reachable == 0:
        return "down"
    return "degraded"


# TODO: Estático, pasar a dinamico si se incorporan más APIs.
def register(mcp: FastMCP):
    @mcp.tool()
    @log_tool_invocation
    async def health_check() -> dict:
        """Comprueba la salud de las apis haciendo una llamada a cada una

        Returns:
            dict: Diccionario con estado, timestamp e integraciones
        """
        weather, guardian = await asyncio.gather(
            _probe_weather(),
            _probe_guardian(),
        )
        integrations = {"weather": weather, "guardian": guardian}
        return {
            "status": _aggregate_status(integrations),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "integrations": integrations,
        }
