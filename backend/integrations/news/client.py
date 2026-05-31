# Constants
from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult
from datetime import date
from datetime import timedelta


from backend.config.settings import settings


class GuardianAPI(BaseAPI):

    BASE_URL = "https://content.guardianapis.com/"

    API_KEY = settings.guardian_api_key  # Key ya validada
    API_KEY_PARAM = "api-key"

    async def search_articles(
        self, topic: str | None = None, days: int = 7
    ) -> ToolResult:
        """Buscar artículos de The Guardian.


        Args:
            topic (str, optional): keyword(s) de búsqueda libre. Si se omite, devuelve
                los artículos más recientes sin filtrar por tema. Defaults to None.

            days (int, optional): número de días hacia atrás desde hoy para acotar la
                búsqueda. Defaults to 7.

        Params enviados:
            - q: <topic> CONDICIONAL!
            - from-date:  YYYY-MM-DD
            - sort: newest

        Respuesta de llamada a endpoint (campos consumidos):
            response.results[].webUrl    → url
            response.results[].webTitle  → title
            response.results[].webPublicationDate   → date

        Returns:
            ToolResult.ok([{title, url, date}, ...]) si hay artículos.
            ToolResult.fail("No articles found") si results está vacío o ausente.
        """
        today = date.today()
        new_date = today - timedelta(days=days)
        params = {"from-date": new_date}
        if topic:
            params["q"] = topic

        endpoint = "search"
        response = await self.make_request(endpoint, "get", params)

        if not response.success or not response.has_content():
            return ToolResult.fail("No articles found")

        results = response.data.get("response", {}).get("results")

        if not results:
            return ToolResult.fail("No articles found")

        articles = [
            {
                "title": article.get("webTitle"),
                "url": article.get("webUrl"),
                "date": article.get("webPublicationDate"),
            }
            for article in results
        ]

        return ToolResult.ok(articles)
