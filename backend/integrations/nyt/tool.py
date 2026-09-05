"""
News API for The New York Times (NYT)
"""

from typing import TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from backend.core.observability import log_tool_invocation
from backend.integrations.metadata import tool_meta
from backend.integrations.nyt.client import NYTAPI


class Articulo(TypedDict):
    """Un artículo del New York Times.

    Todos los campos son opcionales porque el cliente los extrae con ``.get()``.

    ``print_headline`` es el titular de la edición impresa, y no siempre coincide
    con el de web: esa discrepancia es material de análisis en sí misma, porque
    la versión impresa suele ser la sobria.
    """

    title: str | None
    print_headline: str | None
    url: str | None
    date: str | None
    content: str | None  # el `abstract`, lo que alimenta la incoherencia


def register(mcp: FastMCP):

    api = NYTAPI()

    @mcp.tool(meta=tool_meta("Fuentes de contenido", __name__))
    @log_tool_invocation
    async def get_nyt_news(
        topic: str | None = Field(
            default=None,
            description="Palabra(s) clave del tema a buscar, en inglés (ej. 'artificial intelligence', 'climate change'). Si se omite, devuelve las noticias más recientes.",
        ),
        days: int = Field(
            default=7, ge=1, le=30, description="Días hacia atrás desde hoy (1-30)."
        ),
    ) -> list[Articulo]:
        """Busca noticias del New York Times. Se puede indicar de hace cuantos días buscar(por defecto, última semana)

        Args:
            topic (str, Optional): keyword(s) sobre los que buscar artículos (ej. "AI", "elecciones", "climate change").
            days (int, Optional): número de días que se incluyen en la busqueda desde hoy (Default = 7)

        Returns:
            Lista de artículos {title, print_headline, url, date, content}, donde
            `content` es el abstract — lo que necesita
            `detect_clickbait_incoherence`.

        Raises:
            Si no hay resultados o la API falla.
        """
        response = await api.search_articles(topic, days)
        if not response.has_content():
            raise ToolError(response.error or "Error fetching news")
        return response.unwrap()
