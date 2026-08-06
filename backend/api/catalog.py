"""Construcción del catálogo de herramientas — ``GET /tools``.

A diferencia de ``/analyze``, que importa el núcleo directamente, aquí se habla
**MCP de verdad**: el catálogo se construye por descubrimiento
(*handshake*), porque debe reflejar lo que hay conectado en ese momento y no una
lista escrita a mano. Importar módulos daría siempre la misma respuesta aunque
el servidor estuviera caído — que es justo lo contrario de lo que se quiere
mostrar.

**Sesión por petición, no persistente.** El catálogo se consulta cuando alguien
abre la pantalla de Sistema, no en bucle, así que los ~0,2 s del handshake son
imperceptibles. Mantener la sesión viva a cambio obligaría a gestionar
reconexión, guardar estado mutable compartido y responder si ``ClientSession``
aguanta uso concurrente. Se paga esa complejidad cuando haya un consumidor
caliente que la justifique —el agente, con muchas invocaciones por turno— y con
una medición delante.

Tiene un efecto secundario que la hace más atractiva: **la API no necesita
conectarse al arrancar**. Arranca siempre, y ``/tools`` informa del estado real
en el momento de la llamada.

**Un servidor caído no rompe la respuesta.** Sale en ``servers`` con estado
``unreachable`` y su motivo, y las herramientas de los demás se sirven igual.
Es el mismo patrón que las señales de ``/analyze``.
"""

import asyncio

import httpx
import structlog
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool

from backend.api.schemas import (
    CatalogResponse,
    Dimension,
    ServerInfo,
    ServerStatus,
    SignalType,
    ToolInfo,
    ToolModelCard,
)
from backend.config.settings import settings
from backend.integrations.nlp.model_cards import cards_by_signal

log = structlog.get_logger()


def _http_client() -> httpx.AsyncClient:
    """Cliente HTTP para hablar con un servidor MCP.

    Aislado en una función para que los tests lo sustituyan por uno montado
    sobre ``ASGITransport`` y hablen el protocolo en el mismo proceso, sin abrir
    puertos. El timeout es lo que distingue «caído» de «colgado»: sin él, un
    servidor que acepta la conexión y no contesta dejaría ``/tools`` esperando.
    """
    return httpx.AsyncClient(timeout=settings.mcp_timeout)


async def fetch_catalog() -> CatalogResponse:
    """Consulta todos los servidores configurados y funde sus catálogos."""
    resultados = await asyncio.gather(
        *(_consultar(url) for url in settings.mcp_servers),
        return_exceptions=True,
    )

    servers: list[ServerInfo] = []
    tools: list[ToolInfo] = []

    # gather conserva el orden de entrada, así que cada resultado corresponde a
    # la URL de su misma posición.
    for url, resultado in zip(settings.mcp_servers, resultados, strict=True):
        if isinstance(resultado, BaseException):
            log.warning(
                "catalogo.servidor_inalcanzable", url=url, motivo=str(resultado)
            )
            servers.append(
                ServerInfo(
                    url=url,
                    status=ServerStatus.UNREACHABLE,
                    detail=f"{type(resultado).__name__}: {resultado}",
                )
            )
            continue

        info, del_servidor = resultado
        servers.append(info)
        tools.extend(del_servidor)

    return CatalogResponse(servers=servers, tools=tools)


async def _consultar(url: str) -> tuple[ServerInfo, list[ToolInfo]]:
    """Abre una sesión MCP, se presenta y pide el catálogo de ese servidor."""
    async with (
        _http_client() as http_client,
        streamable_http_client(url, http_client=http_client) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        inicializacion = await session.initialize()
        listado = await session.list_tools()

    nombre = inicializacion.serverInfo.name
    herramientas = [_envolver(tool, nombre) for tool in listado.tools]

    return (
        ServerInfo(
            url=url,
            name=nombre,
            status=ServerStatus.OK,
            tool_count=len(herramientas),
        ),
        herramientas,
    )


def _envolver(tool: Tool, servidor: str) -> ToolInfo:
    """Traduce una ``Tool`` del protocolo al contrato del catálogo."""
    meta = tool.meta or {}

    return ToolInfo(
        name=tool.name,
        description=tool.description,
        input_schema=tool.inputSchema,
        category=meta.get("category"),
        integration=meta.get("integration"),
        server=servidor,
        model_card=_ficha_de(tool.name),
    )


def _ficha_de(nombre: str) -> ToolModelCard | None:
    """Busca la ficha de modelo de una tool, si es una señal de análisis.

    El índice vive en ``model_cards`` porque lo comparte con la orquestación de
    ``/analyze``: dos copias acabarían divergiendo. Devuelve None para las
    herramientas que no son señales — fuentes de contenido y utilidades.
    """
    card = cards_by_signal().get(nombre)
    if card is None:
        return None

    return ToolModelCard(
        type=SignalType(card["type"]),
        dimension=Dimension(card["dimension"]),
        limitations=card["limitations"],
    )
