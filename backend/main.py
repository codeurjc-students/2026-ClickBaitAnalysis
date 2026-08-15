"""
Servidor MCP principal.
"""

import structlog
from mcp.server.fastmcp import FastMCP

from backend.config.settings import settings
from backend.core import health
from backend.core.logging import configure_logging
from backend.integrations.discovery import discover_and_register

log = structlog.get_logger()
mcp = FastMCP("tfg-mcp-server")


# Integraciones: se descubren solas recorriendo backend/integrations/.
# Añadir una fuente o una señal es crear su paquete; este fichero no se toca.
integraciones = discover_and_register(mcp)

# El chequeo de salud va aparte porque NO es una integración: no envuelve
# ninguna API externa, es infraestructura básica.
health.register(mcp)


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
