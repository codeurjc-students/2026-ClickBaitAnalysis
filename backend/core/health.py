import asyncio
from datetime import UTC, datetime
from typing import Literal, TypedDict

import httpx
from mcp.server.fastmcp import FastMCP

from backend.config.settings import settings
from backend.core.errores import describir_error
from backend.core.observability import log_tool_invocation
from backend.integrations.metadata import tool_meta

PROBE_TIMEOUT = 5


class Sonda(TypedDict):
    """Resultado de sondear una integración."""

    reachable: bool
    error: str | None


class Salud(TypedDict):
    """Estado agregado del sistema y de cada integración por separado.

    Se devuelven las dos cosas a propósito: el agregado sirve para un semáforo,
    pero sin el detalle por integración no se puede saber **cuál** falla.
    """

    status: Literal["ok", "degraded", "down"]
    timestamp: str
    integrations: dict[str, Sonda]


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


async def _probe(url: str, params: dict | None = None) -> Sonda:
    """Hace una petición ligera a una API y reporta si responde correctamente.

    El `error` lo redacta `describir_error`, nunca se reenvía `str(exc)`. Medido
    el 2026-09-17 (#163): con un 401, el mensaje de httpx es «Client error '401
    Unauthorized' for url '…?api-key=…'» — la URL entera, y Guardian y NYT
    llevan la clave en ella. Y este texto es público: sale por `GET /health`, lo
    pinta el indicador de la cabecera y lo recibe por MCP quien llame a
    `health_check`, el LLM del agente incluido.

    Los fallos de red salieron limpios al medirlos, pero sólo se midieron dos
    tipos de los que puede lanzar httpx: también se reducen al nombre del tipo.
    De paso deja de haber errores vacíos — un timeout daba `""`, y el indicador
    decía «no responde» sin ningún motivo.
    """
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()  # Evita tratar 4xx/5xx como respuesta aceptable
        return {"reachable": True, "error": None}
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": describir_error(exc)}


def _aggregate_status(integrations: dict) -> Literal["ok", "degraded", "down"]:
    reachable = sum(1 for i in integrations.values() if i["reachable"])
    total = len(integrations)
    if reachable == total:
        return "ok"
    if reachable == 0:
        return "down"
    return "degraded"


async def check_health() -> Salud:
    """Sondea todas las integraciones y agrega su estado.

    Vive fuera de ``register`` porque lo consumen DOS fachadas: la tool MCP de
    abajo y ``GET /health`` de la API REST. Duplicar el sondeo llevaría a
    que las dos respondieran cosas distintas.
    """
    results = await asyncio.gather(*(_probe(**cfg) for cfg in PROBES.values()))
    integrations = dict(zip(PROBES, results, strict=True))
    return {
        "status": _aggregate_status(integrations),
        "timestamp": datetime.now(UTC).isoformat(),
        "integrations": integrations,
    }


def register(mcp: FastMCP):
    # `integration` sale None: vive en core/ y no envuelve ninguna fuente
    # externa. Es infraestructura, no una integración.
    @mcp.tool(meta=tool_meta("Utilidades", __name__))
    @log_tool_invocation
    async def health_check() -> Salud:
        """Comprueba la salud de las apis haciendo una llamada a cada una

        Returns:
            dict: Diccionario con estado, timestamp e integraciones
        """
        return await check_health()
