"""
News API for The New York Times (NYT)
"""

import json

from mcp.server.fastmcp import FastMCP

from backend.core.observability import log_tool_invocation
from backend.integrations.nyt.client import NYTAPI
from backend.core.models import ToolResult


def register(mcp: FastMCP):

    api = NYTAPI()

    @mcp.tool()
    @log_tool_invocation
    async def get_nyt_news(topic: str) -> str:
        """Buscar noticias del New York Times de la última semana sobre un tema concreto.

        Args:
            topic (str): keyword(s) sobre los que buscar artículos (ej. "AI", "elecciones", "climate change").

        Returns:
            JSON serializado con lista de artículos {title, url, date}, o un mensaje de error
            si no hay resultados o la API falla
        """
        response = await api.search_articles(topic)
        if not response.has_content():
            return response.error or "Error fetching news"
        return json.dumps(response.data)
