"""Noticias en español de GNews (#235).

Una de las dos fuentes en español; la otra es NewsData.io (`get_newsdata_news`).
Devuelve lo mismo que las de NYT y Guardian —una lista de artículos con su
cuerpo en `content`— más el medio en `source`, porque aquí cada noticia puede
venir de un medio y de un país distintos.
"""

from typing import Annotated, TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from backend.core.observability import log_tool_invocation
from backend.core.texto import TextoOpcional
from backend.integrations.gnews.client import GNewsAPI
from backend.integrations.metadata import tool_meta


class Articulo(TypedDict):
    """Una noticia de GNews.

    Todos los campos son opcionales porque el cliente los extrae con ``.get()``:
    la API no garantiza que estén.
    """

    title: str | None
    url: str | None
    date: str | None  # ISO 8601, en UTC
    content: str | None  # la `description`, lo que alimenta la incoherencia
    source: str | None  # el nombre del medio


def register(mcp: FastMCP):

    api = GNewsAPI()

    @mcp.tool(meta=tool_meta("Fuentes de contenido", __name__))
    @log_tool_invocation
    async def get_gnews_news(
        # «None» escrito como tema es buscar sin tema, no buscar la palabra (#197).
        topic: Annotated[
            TextoOpcional,
            Field(
                description="Palabra(s) clave del tema a buscar, en español (ej. 'inteligencia artificial', 'elecciones'). Si se omite, devuelve los titulares destacados.",
            ),
        ] = None,
        days: int = Field(
            default=7, ge=1, le=30, description="Días hacia atrás desde hoy (1-30)."
        ),
    ) -> list[Articulo]:
        """Busca noticias en español, de medios de varios países, en GNews; a diferencia de `get_newsdata_news`, se puede indicar de hace cuántos días buscar (por defecto, la última semana; hasta 30).

        Args:
            topic (str, Optional): palabras clave en español sobre las que buscar (ej. "inteligencia artificial", "elecciones").
            days (int, Optional): número de días que se incluyen en la búsqueda desde hoy (Default = 7)

        Returns:
            Lista de noticias {title, url, date, content, source}, donde
            `content` es la entradilla — lo que necesita
            `detect_clickbait_incoherence` — y `source`, el medio.

        Raises:
            Si no hay resultados, la API falla o GNews no está configurado.
        """
        response = await api.search_articles(topic, days)
        if not response.has_content():
            raise ToolError(response.error or "Error fetching news")
        return response.unwrap()
