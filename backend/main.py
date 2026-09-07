"""
Servidor MCP principal.
"""

import structlog
from mcp.server.fastmcp import FastMCP

from backend.analysis import tool as analysis_tool
from backend.config.settings import settings
from backend.core import health
from backend.core.logging import configure_logging
from backend.integrations.discovery import discover_and_register

log = structlog.get_logger()
mcp = FastMCP("tfg-mcp-server")


# Integraciones: se descubren solas recorriendo backend/integrations/.
# Añadir una fuente o una señal es crear su paquete; este fichero no se toca.
integraciones = discover_and_register(mcp)

# Lo que NO es una integración se registra a mano: `discover_and_register` sólo
# recorre `integrations/`, y estas dos no viven ahí ni envuelven nada externo.
#
# - El chequeo de salud es infraestructura básica.
# - El análisis completo es lógica de dominio, y registrarlo desde su propio
#   paquete evita el ciclo que habría si lo hiciera `integrations/nlp/tool.py`:
#   `analysis` ya importa las señales de `nlp`.
#
# Es lo que hace que el agente conversacional pueda reproducir el veredicto del
# formulario en vez de tener que recomponerlo desde las señales sueltas (#107).
health.register(mcp)
analysis_tool.register(mcp)


def main():
    # Initialize and run the server
    configure_logging()

    # host/port los ignora el transporte stdio.
    mcp.settings.host = settings.mcp_host
    mcp.settings.port = settings.mcp_port

    log.info(
        "server.start",
        server="tfg-mcp-server",
        transport=settings.mcp_transport,
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=settings.log_level,
        log_format=settings.log_format,
        # Qué se descubrió. Si una integración falló al cargar, sus tools no
        # existen y el sistema queda degradado en silencio: aquí es donde se ve.
        integraciones=list(integraciones.registered),
        integraciones_fallidas=integraciones.failed or None,
    )
    mcp.run(transport=settings.mcp_transport)


if __name__ == "__main__":
    main()
