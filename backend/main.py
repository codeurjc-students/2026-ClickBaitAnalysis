"""
Servidor MCP principal.
"""

from backend.core.logging import configure_logging
import structlog


from mcp.server.fastmcp import FastMCP

from backend.integrations.news import tool as news_tool
from backend.integrations.weather import tool as weather_tool

log = structlog.get_logger()
mcp = FastMCP("tfg-mcp-server")

# TODO: Implementar register dinámico
weather_tool.register(mcp)
news_tool.register(mcp)


def main():
    # Initialize and run the server
    configure_logging()
    log.info("server.start", transport="stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
