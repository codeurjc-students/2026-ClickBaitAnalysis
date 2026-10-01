"""La salud de las integraciones: ¿responden las APIs de noticias?

Sondea `weather`, `guardian` y `nyt` en paralelo, con una petición ligera a
cada una, y lo publica por dos fachadas que comparten `check_health`: `GET
/health` de la API REST y la tool MCP `health_check`, que se registra aquí.

Dos límites que el nombre no dice:

- **No cubre las señales NLP** (#147). Un verde aquí no dice nada de
  `detect_clickbait`; la sonda útil sería por modelo, y no existe.
- **Cada sondeo son tres peticiones externas reales**, con NYT limitado a 500
  al día. Por eso se cachea `health_cache_s` (#169), y por eso el healthcheck
  de compose no usa `/health` (#164).
"""

import asyncio
import time
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


async def _sondear() -> Salud:
    """Pregunta de verdad a las tres APIs, en paralelo."""
    results = await asyncio.gather(*(_probe(**cfg) for cfg in PROBES.values()))
    integrations = dict(zip(PROBES, results, strict=True))
    return {
        "status": _aggregate_status(integrations),
        "timestamp": datetime.now(UTC).isoformat(),
        "integrations": integrations,
    }


_CERROJO = asyncio.Lock()
_ultimo: Salud | None = None
_vale_hasta: float = 0.0


async def check_health() -> Salud:
    """El estado de las integraciones, sondeado como mucho cada `health_cache_s`.

    Vive fuera de ``register`` porque lo consumen DOS fachadas: la tool MCP de
    abajo y ``GET /health`` de la API REST. Duplicar el sondeo llevaría a que
    las dos respondieran cosas distintas.

    **La caché es lo único que acota la cuota** (#169). Cada sondeo son tres
    peticiones externas reales y el indicador de la cabecera lo pide al cargar
    cualquier pantalla, con NYT limitado a 500 llamadas diarias. El límite de
    velocidad por cliente reparte el abuso pero no lo acota: cien clientes
    distintos agotan la cuota igual. Esto la acota pase lo que pase.

    **No enmascara nada**, porque el ``timestamp`` es el DEL SONDEO: una
    respuesta cacheada dice su propia edad y quien la lea puede decidir si le
    vale. Por eso no hizo falta tocar el contrato.

    Ojo: la caché es **de este proceso**. La API y el servidor MCP son dos, así
    que cada uno tiene la suya y entre los dos pueden sondear el doble.
    """
    global _ultimo, _vale_hasta

    if settings.health_cache_s <= 0:
        return await _sondear()

    if _ultimo is not None and time.monotonic() < _vale_hasta:
        return _ultimo

    async with _CERROJO:
        # Se vuelve a mirar ya dentro: si llegan diez peticiones a la vez, las
        # nueve que esperaban aquí encuentran el sondeo hecho. Sin esta segunda
        # comprobación harían diez sondeos en fila, que es el caso que más
        # importa —una pantalla que se abre en varias pestañas a la vez.
        if _ultimo is not None and time.monotonic() < _vale_hasta:
            return _ultimo

        _ultimo = await _sondear()
        _vale_hasta = time.monotonic() + settings.health_cache_s
        return _ultimo


def olvidar_sondeo() -> None:
    """Tira la caché.

    La usan las pruebas: es estado de módulo, así que sin esto lo que sondea un
    test se lo encuentra el siguiente y los dobles de `respx` del segundo no
    llegarían a usarse nunca.
    """
    global _ultimo, _vale_hasta
    _ultimo = None
    _vale_hasta = 0.0


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
