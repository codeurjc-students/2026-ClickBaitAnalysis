import asyncio
from datetime import datetime, timezone
from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP

from backend.config.settings import settings
from backend.core.observability import log_tool_invocation

PROBE_TIMEOUT = 5

PROBES = {
    "weather": {
        "url": "https://api.weather.gov/",
    },
    "guardian": {
        "url": "https://content.guardianapis.com/search",
        "params": {"page-size": 1, "api-key": settings.guardian_api_key},
    },
    "nyt": {
        "url": "https://api.nytimes.com/svc/search/v2/articlesearch.json",
        "params": {"api-key": settings.nyt_api_key},
    },
}


async def _probe(url: str, params: dict | None = None) -> dict:
    """Hace una petición ligera a una API y reporta si responde correctamente."""
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()  # Evita tratar 4xx/5xx como respuesta aceptable
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


def register(mcp: FastMCP):
    @mcp.tool()
    @log_tool_invocation
    async def health_check() -> dict:
        """Comprueba la salud de las apis haciendo una llamada a cada una

        Returns:
            dict: Diccionario con estado, timestamp e integraciones
        """
        results = await asyncio.gather(*(_probe(**cfg) for cfg in PROBES.values()))
        integrations = dict(zip(PROBES, results))
        return {
            "status": _aggregate_status(integrations),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "integrations": integrations,
        }
