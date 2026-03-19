"""
Servidor MCP principal.
"""

import logging

from mcp.server.fastmcp import FastMCP

from backend.tools import weather_tool



mcp = FastMCP("tfg-mcp-server")

#TODO: Implementar register dinámico
weather_tool.register(mcp)


def main():
    # Initialize and run the server
    logging.info("Starting server...")
    mcp.run(transport="stdio")
    


if __name__ == "__main__":
    main()

