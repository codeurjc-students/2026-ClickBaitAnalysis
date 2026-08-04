"""
Servidor MCP principal.
"""

import structlog
from mcp.server.fastmcp import FastMCP

from backend.config.settings import settings
from backend.core import health
from backend.core.logging import configure_logging
from backend.integrations.guardian import tool as guardian_tool
from backend.integrations.nlp import tool as nlp_tool
from backend.integrations.nyt import tool as nyt_tool
from backend.integrations.weather import tool as weather_tool

log = structlog.get_logger()
mcp = FastMCP("tfg-mcp-server")


# APIS
weather_tool.register(mcp)
guardian_tool.register(mcp)
nyt_tool.register(mcp)

# NLP
nlp_tool.register(mcp)

# Health check
health.register(mcp)


def main():
    # Initialize and run the server
    configure_logging()
    log.info(
        "server.start",
        server="tfg-mcp-server",
        transport="stdio",
        log_level=settings.log_level,
        log_format=settings.log_format,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
