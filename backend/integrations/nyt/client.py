from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult
from datetime import date
from datetime import timedelta


from backend.config.settings import settings


class NYTAPI(BaseAPI):

    BASE_URL = "https://api.nytimes.com/svc/search/v2/"

    API_KEY = settings.nyt_api_key  # Key ya validada
    API_KEY_PARAM = "api-key"

    async def search_articles(
        self, topic: str | None = None, days: int = 7
    ) -> ToolResult:
        """Buscar artículos del NYT.


        Llama a Article Search API (https://developer.nytimes.com/docs/articlesearch-product/1/overview).


        Args:
            topic (str, optional): keyword(s) de búsqueda libre. Si se omite, devuelve
                los artículos más recientes sin filtrar por tema. Defaults to None.

            days (int, optional): número de días hacia atrás desde hoy para acotar la
                búsqueda. Defaults to 7.

        Params enviados:
            - q: <topic> CONDICIONAL!
            - begin_date: YYYYMMDD
            - sort: newest

        Respuesta de llamada a endpoint (campos consumidos):
            response.docs[].web_url    → url
            response.docs[].headline.main  → title
            response.docs[].pub_date   → date

        Returns:
            ToolResult.ok([{title, url, date}, ...]) si hay artículos.
            ToolResult.fail("No articles found") si docs está vacío o ausente.
        """
        today = date.today()
        new_date = (today - timedelta(days=days)).strftime("%Y%m%d")  # Formato YYYYMMDD
        params = {"begin_date": new_date, "sort": "relevance" if topic else "newest"}
        if topic:
            params["q"] = topic

        endpoint = "articlesearch.json"
        response = await self.make_request(endpoint, "get", params)

        if not response.success or not response.has_content():
            return ToolResult.fail("No articles found")

        results = response.data.get("response", {}).get("docs")

        if not results:
            return ToolResult.fail("No articles found")

        articles = [
            {
                "title": article.get("headline", {}).get("main"),
                # De nuevo, sin {}, el primer get devuelve none y ahí no se puede hacer get.
                "url": article.get("web_url"),
                "date": article.get("pub_date"),
            }
            for article in results
        ]

        return ToolResult.ok(articles)
