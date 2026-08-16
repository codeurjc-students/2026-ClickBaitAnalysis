# Constants
from datetime import UTC, datetime, timedelta

from backend.config.settings import settings
from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult


class GuardianAPI(BaseAPI):
    BASE_URL = "https://content.guardianapis.com/"

    API_KEY = settings.guardian_api_key  # Key ya validada
    API_KEY_PARAM = "api-key"

    RATE_CALLS = 60
    RATE_PERIOD = 60

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
            response.results[].fields.trailText   → content

        Returns:
            ToolResult.ok([{title, url, date, content}, ...]) si hay artículos.
            ToolResult.fail("No articles found") si results está vacío o ausente.
        """
        # UTC explícito, no la zona de la máquina: en Docker el contenedor va en
        # UTC y el equipo de desarrollo no, así que `date.today()` desplazaría la
        # ventana de búsqueda un día cerca de medianoche según dónde se ejecute.
        today = datetime.now(UTC).date()
        new_date = today - timedelta(days=days)
        params = {"from-date": new_date, "show-fields": "trailText"}
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
                "content": article.get("fields", {}).get("trailText"),
            }
            for article in results
        ]

        return ToolResult.ok(articles)

    # Busqueda por tags especifica de The guardian

    # Fix: No coger tags[0] ya que suelen ser niches, para tema principal sistema X/X
    async def _find_tag(self, topic: str) -> str | None:
        result = await self.make_request("tags", "get", {"q": topic, "page-size": 10})
        if not result.success:
            return None
        tags = result.data.get("response", {}).get("results", [])
        if not tags:
            return None

        for t in tags:
            parts = t.get("id", "").split("/")  # Divid parts por /
            if len(parts) == 2 and parts[0] == parts[1]:  # Si las dos coinciden
                return t.get("id")
        return tags[0].get("id")

    def _read_quota(self, response):
        val = response.headers.get("x-ratelimit-remaining-day")
        self._remaining = int(val) if val is not None else None
