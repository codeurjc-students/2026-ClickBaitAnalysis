"""Apertura de sesiones MCP.

Extraído porque lo comparten dos consumidores —el catálogo y la ejecución de
herramientas— y duplicar el montaje de tres gestores de contexto anidados era
pedir que se desincronizaran.

Vive en ``core/`` desde #137. Estuvo en ``api/`` por el orden en que se
construyó el sistema, no por diseño: no importa nada de la fachada REST, y el
agente de R13 necesita exactamente esto para descubrir herramientas. Desde
``api/`` no podía usarlo — ``tests/test_arquitectura.py`` prohíbe que el núcleo
importe de las fachadas.

**Sesión por petición, no persistente.** Ni el catálogo ni la ejecución son
endpoints calientes: se consultan cuando alguien abre una pantalla o pulsa un
botón, así que los ~0,2 s del handshake son imperceptibles. Mantener la sesión
viva obligaría a gestionar reconexión, estado mutable compartido y uso
concurrente de ``ClientSession``. Como efecto secundario, **la API no necesita
conectarse al arrancar**: arranca siempre e informa del estado real en cada
llamada.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import InitializeResult


def _http_client(timeout: float) -> httpx.AsyncClient:
    """Cliente HTTP para hablar con un servidor MCP.

    Aislado en una función para que los tests lo sustituyan por uno montado
    sobre ``ASGITransport`` y hablen el protocolo en el mismo proceso, sin abrir
    puertos. El timeout es lo que distingue «caído» de «colgado»: sin él, un
    servidor que acepta la conexión y no contesta dejaría la petición esperando.
    """
    return httpx.AsyncClient(timeout=timeout)


@asynccontextmanager
async def open_session(
    url: str,
    timeout: float,  # noqa: ASYNC109
) -> AsyncGenerator[tuple[ClientSession, InitializeResult]]:
    """Abre una sesión MCP ya inicializada contra ``url``.

    Sobre el ``noqa``: ruff señala el parámetro ``timeout`` y recomienda
    ``asyncio.timeout``, y **tenía razón** — así se descubrió #113, donde una
    herramienta lenta colgaba la petición para siempre porque este timeout no
    cortaba. Pero la solución no fue quitarlo sino **sumarle** el otro: quien
    llama envuelve la operación en ``asyncio.timeout`` para acotar la DURACIÓN, y
    éste se conserva porque cubre algo distinto que aquél no ve — un servidor que
    acepta la conexión y deja de enviar bytes. Son dos fallos diferentes y hacen
    falta los dos cortes.

    Devuelve también el resultado del *handshake*, porque de ahí sale el nombre
    que **declara el propio servidor** (``serverInfo.name``) — no el que figure
    en la configuración.

    Las tres capas, de dentro afuera: el cliente httpx pone el transporte y el
    timeout, ``streamable_http_client`` traduce HTTP a los dos flujos que MCP
    necesita, y ``ClientSession`` habla el protocolo sobre ellos. Se cierran en
    orden inverso.
    """
    async with (
        _http_client(timeout) as http_client,
        streamable_http_client(url, http_client=http_client) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        inicializacion = await session.initialize()
        yield session, inicializacion
