"""Cliente de GNews, una de las dos fuentes de noticias en español (#235).

Con tema busca en `/search`; sin él, en `/top-headlines` (los titulares
destacados), porque `/search` exige `q`. Siempre con `lang=es` y sin filtrar por
país: lo que se pide son noticias en español, no de un país concreto.

Lo que no se deduce de aquí, medido con `spikes/noticias_es.py` (9 oct 2026):

- El `content` del plan gratuito llega RECORTADO (265–267 caracteres, con una
  marca de lo que falta), así que el cuerpo que se devuelve es `description`,
  una entradilla entera (103–420 caracteres en lo medido). Es lo que lee la
  incoherencia.
- Lo más reciente tiene unas 12 horas: el plan gratuito sirve con retraso.
- La misma noticia llega a veces repetida (la búsqueda de hace 30 a 25 días
  trajo dos veces el mismo titular): se queda la primera de cada titular
  (`_sin_repetidos`), como en NewsData.io.
- La cuota no sale en ninguna cabecera, así que la restante es la que cuenta
  este proceso (`DAILY_LIMIT`), como en NYT.
- Una clave que no existe da 400 («You did not provide an API key.», como si
  faltara), no 401, y el cuerpo no la repite.

La clave es opcional (`settings.gnews_api_key`): sin ella no se hace ninguna
petición, y el fallo dice qué falta. Por la cuota, GNews no tiene sonda en
`/health`: con su caché de 30 s podría gastar las 100 peticiones del día.
"""

from datetime import UTC, datetime, timedelta

from backend.config.settings import settings
from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult

SIN_CLAVE = "GNews no está configurado: falta GNEWS_API_KEY en la configuración."


def _sin_repetidos(articulos: list[dict]) -> list[dict]:
    """La primera noticia de cada titular, en el orden en que llegaron.

    Las que no traen titular se quedan todas: no hay con qué compararlas. La
    misma regla está en el cliente de NewsData.io.
    """
    vistos: set[str] = set()
    unicos = []
    for articulo in articulos:
        titulo = articulo["title"]
        if titulo is not None and titulo in vistos:
            continue
        if titulo is not None:
            vistos.add(titulo)
        unicos.append(articulo)
    return unicos


class GNewsAPI(BaseAPI):
    BASE_URL = "https://gnews.io/api/v4/"

    API_KEY = (
        settings.gnews_api_key.get_secret_value() if settings.gnews_api_key else None
    )
    API_KEY_PARAM = "apikey"

    # El plan gratuito: una petición por segundo y 100 al día, con 30 días de
    # archivo (de ahí el tope de `days` en la herramienta).
    RATE_CALLS = 1
    RATE_PERIOD = 1

    DAILY_LIMIT = 100

    async def search_articles(
        self, topic: str | None = None, days: int = 7
    ) -> ToolResult:
        """Buscar noticias en español en GNews.

        Llama a la API v4 de GNews (https://docs.gnews.io/).

        Args:
            topic (str, optional): palabras clave. Si se omite, devuelve los
                titulares destacados. Defaults to None.

            days (int, optional): número de días hacia atrás desde ahora; el
                plan gratuito no sirve más de 30. Defaults to 7.

        Params enviados:
            - q: <topic> CONDICIONAL! (sólo en `/search`)
            - lang: es
            - max: 10 (el máximo del plan gratuito)
            - from: YYYY-MM-DDTHH:MM:SSZ

        Sin `sortby`: GNews ordena por fecha, lo más reciente primero.

        Respuesta de llamada a endpoint (campos consumidos):
            articles[].title        → title
            articles[].url          → url
            articles[].publishedAt  → date (ISO 8601, en UTC)
            articles[].description  → content
            articles[].source.name  → source

        Returns:
            ToolResult.ok([{title, url, date, content, source}, ...]) si hay
                artículos, sin titulares repetidos.
            ToolResult.fail("No articles found") si `articles` está vacío o ausente.
            ToolResult.fail(SIN_CLAVE) sin clave, sin llamar a la API.
            El error de `make_request`, tal cual, si la petición falla.
        """
        if not self.API_KEY:
            return ToolResult.fail(SIN_CLAVE)

        # UTC explícito, como en NYT: la ventana no depende de la zona de la
        # máquina que ejecuta.
        desde = datetime.now(UTC) - timedelta(days=days)
        params = {"lang": "es", "max": 10, "from": desde.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if topic:
            params["q"] = topic

        endpoint = "search" if topic else "top-headlines"
        response = await self.make_request(endpoint, "get", params)

        # Un fallo NO es «no hay noticias» (#196, #212): el agente decide con
        # este mensaje, y creyendo que no hay nada gastaría cuota con otros temas.
        if not response.success:
            return response

        if not response.has_content():
            return ToolResult.fail("No articles found")

        results = response.unwrap().get("articles")

        if not results:
            return ToolResult.fail("No articles found")

        articles = [
            {
                "title": article.get("title"),
                "url": article.get("url"),
                "date": article.get("publishedAt"),
                # El `content` viene recortado en el plan gratuito: ver arriba.
                "content": article.get("description"),
                "source": (article.get("source") or {}).get("name"),
            }
            for article in results
        ]

        return ToolResult.ok(_sin_repetidos(articles))
