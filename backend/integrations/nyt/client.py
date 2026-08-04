from datetime import datetime, timedelta, timezone

from backend.config.settings import settings
from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult


class NYTAPI(BaseAPI):
    BASE_URL = "https://api.nytimes.com/svc/search/v2/"

    API_KEY = settings.nyt_api_key  # Key ya validada
    API_KEY_PARAM = "api-key"

    RATE_CALLS = 5  # Crea una instancia nueva con rate calls, no pasar por atributo o todos usan el mismo objecto.
    RATE_PERIOD = 60

    DAILY_LIMIT = 500

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
            response.docs[].headline.print_headline  → print_headline
            response.docs[].pub_date   → date
            response.docs[].abstract   → content

        Returns:
            ToolResult.ok([{title, print_headline, url, date, content}, ...]) si hay artículos.
            ToolResult.fail("No articles found") si docs está vacío o ausente.
        """
        # UTC explícito, no la zona de la máquina: en Docker el contenedor va en
        # UTC y el equipo de desarrollo no, así que `date.today()` desplazaría la
        # ventana de búsqueda un día cerca de medianoche según dónde se ejecute.
        today = datetime.now(timezone.utc).date()
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
                "print_headline": article.get("headline", {}).get("print_headline"),
                # De nuevo, sin {}, el primer get devuelve none y ahí no se puede hacer get.
                "url": article.get("web_url"),
                "date": article.get("pub_date"),
                "content": article.get("abstract"),
            }
            for article in results
        ]

        return ToolResult.ok(articles)
