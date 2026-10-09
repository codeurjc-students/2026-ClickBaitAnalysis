"""Noticias en español de NewsData.io (#235).

Una de las dos fuentes en español; la otra es GNews (`get_gnews_news`). Devuelve
lo mismo que ella. No tiene `days`: el plan gratuito sólo sirve lo último
publicado (ver el cliente).
"""

from typing import Annotated, TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from backend.core.observability import log_tool_invocation
from backend.core.texto import TextoOpcional
from backend.integrations.metadata import tool_meta
from backend.integrations.newsdata.client import NewsDataAPI


class Articulo(TypedDict):
    """Una noticia de NewsData.io.

    Todos los campos son opcionales porque el cliente los extrae con ``.get()``:
    la API no garantiza que estén.
    """

    title: str | None
    url: str | None
    date: str | None  # ISO 8601, en UTC
    content: str | None  # la `description`, lo que alimenta la incoherencia
    source: str | None  # el nombre del medio


def register(mcp: FastMCP):

    api = NewsDataAPI()

    @mcp.tool(meta=tool_meta("Fuentes de contenido", __name__))
    @log_tool_invocation
    async def get_newsdata_news(
        # «None» escrito como tema es buscar sin tema, no buscar la palabra (#197).
        topic: Annotated[
            TextoOpcional,
            Field(
                description="Palabra(s) clave que deben aparecer en el titular, en español (ej. 'inteligencia artificial', 'elecciones'). Si se omite, devuelve las noticias más recientes.",
            ),
        ] = None,
    ) -> list[Articulo]:
        """Busca las noticias más recientes en español, de medios de varios países, en NewsData.io; no se puede elegir de hace cuántos días (para eso, `get_gnews_news`).

        Args:
            topic (str, Optional): palabras clave en español sobre las que buscar (ej. "inteligencia artificial", "elecciones").

        Returns:
            Lista de noticias {title, url, date, content, source}, donde
            `content` es la entradilla — lo que necesita
            `detect_clickbait_incoherence` — y `source`, el medio.

        Raises:
            Si no hay resultados, la API falla o NewsData.io no está configurado.
        """
        response = await api.latest_articles(topic)
        if not response.has_content():
            raise ToolError(response.error or "Error fetching news")
        return response.unwrap()
