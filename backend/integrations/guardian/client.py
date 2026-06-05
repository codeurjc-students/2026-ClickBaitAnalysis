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
            topic (str, optional): tema a buscar. Se resuelve a un tag de The Guardian
                (vía /tags) para filtrar con precisión; si no hay tag, se usa como
                búsqueda libre `q` (fallback). Si se omite, devuelve lo más reciente.
                Defaults to None.

            days (int, optional): número de días hacia atrás desde hoy para acotar la
                búsqueda. Defaults to 7.

        Params enviados:
            - from-date: YYYY-MM-DD
            - tag: <id> si /tags encuentra uno para `topic`; si no, q: <topic> (fallback)

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
        if topic:  # Usa buscador de tags
            tag_id = await self._find_tag(topic)
            if tag_id:
                params["tag"] = tag_id
            else:
                params["q"] = topic  # fallback

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

    # Busqueda por tags especifica de The guardian
    async def _find_tag(self, topic: str) -> str | None:
        result = await self.make_request("tags", "get", {"q": topic, "page-size": 10})
        if not result.success:
            return None
        tags = result.data.get("response", {}).get("results", [])
        return tags[0].get("id") if tags else None
