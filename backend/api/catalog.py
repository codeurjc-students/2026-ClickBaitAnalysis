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

Desde #137 el descubrimiento en sí vive en ``core/mcp/tools.py``, junto con esa
degradación: el agente de R13 querrá un catálogo parcial por el mismo motivo, y
no puede importar de una fachada. Aquí queda la **traducción** al contrato —y la
ficha de modelo de cada señal, que es lo único de esto que conoce el dominio.
"""

import structlog
from mcp.types import Tool

from backend.analysis.domain import Dimension, SignalType
from backend.api.schemas import (
    CatalogResponse,
    ServerInfo,
    ServerStatus,
    ToolInfo,
    ToolModelCard,
)
from backend.config.settings import settings
from backend.core.mcp import tools as mcp_tools
from backend.integrations.nlp.model_cards import cards_by_signal

log = structlog.get_logger()


async def fetch_catalog() -> CatalogResponse:
    """Consulta todos los servidores configurados y funde sus catálogos.

    Es quien **lee la configuración y la pasa**: el mecanismo recibe los
    servidores y el corte por parámetro. Aquí se usa ``mcp_timeout`` y no
    ``mcp_execute_timeout`` porque descubrir tarda milésimas — lo que necesita
    margen es ejecutar.
    """
    resultados = await mcp_tools.discover_all(
        settings.mcp_servers, settings.mcp_timeout
    )

    servers: list[ServerInfo] = []
    tools: list[ToolInfo] = []

    # `discover_all` devuelve una lista del mismo largo y en el mismo orden que
    # las URLs, así que cada resultado corresponde al servidor de su posición.
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

        herramientas = [_envolver(tool, resultado.server) for tool in resultado.tools]
        servers.append(
            ServerInfo(
                url=resultado.url,
                name=resultado.server,
                status=ServerStatus.OK,
                tool_count=len(herramientas),
            )
        )
        tools.extend(herramientas)

    return CatalogResponse(servers=servers, tools=tools)


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
        name=card["name"],
        task=card["task"],
        model_id=card["model_id"],
        type=SignalType(card["type"]),
        dimension=Dimension(card["dimension"]),
        limitations=card["limitations"],
    )
