"""
News API for The Guardian
"""

from typing import TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from backend.core.observability import log_tool_invocation
from backend.integrations.guardian.client import GuardianAPI
from backend.integrations.metadata import tool_meta


class Articulo(TypedDict):
    """Un artículo de The Guardian.

    Todos los campos son opcionales porque el cliente los extrae con ``.get()``:
    la API no garantiza que estén, y declararlos obligatorios haría que el
    esquema publicado prometiera más de lo que se puede cumplir.
    """

    title: str | None
    url: str | None
    date: str | None
    content: str | None  # el teaser (`trailText`), lo que alimenta la incoherencia


def register(mcp: FastMCP):

    api = GuardianAPI()

    @mcp.tool(meta=tool_meta("Fuentes de contenido", __name__))
    @log_tool_invocation
    async def get_guardian_news(
        topic: str | None = Field(
            default=None,
            description="Palabra(s) clave del tema a buscar, en inglés (ej. 'artificial intelligence', 'climate change'). Si se omite, devuelve las noticias más recientes.",
        ),
        days: int = Field(
            default=7, ge=1, le=30, description="Días hacia atrás desde hoy (1-30)."
        ),
    ) -> list[Articulo]:
        """Busca noticias de The Guardian. Se puede indicar de hace cuantos días buscar(por defecto, última semana)

        Args:
            topic (str, Optional): keyword(s) sobre los que buscar artículos (ej. "AI", "elecciones", "climate change").
            days (int, Optional): número de días que se incluyen en la busqueda desde hoy (Default = 7)

        Returns:
            Lista de artículos {title, url, date, content}, donde `content` es el
            teaser — lo que necesita `detect_clickbait_incoherence`.

        Raises:
            Si no hay resultados o la API falla.
        """
        response = await api.search_articles(topic, days)
        if not response.has_content():
            raise ToolError(response.error or "Error fetching news")
        return response.data
