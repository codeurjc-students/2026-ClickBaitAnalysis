"""Cliente de NewsData.io, una de las dos fuentes de noticias en español (#235).

Pide `/latest` (lo último publicado), con tema o sin él, siempre con
`language=es` y sin filtrar por país, como GNews.

Lo que no se deduce de aquí, medido con `spikes/noticias_es.py` (9 oct 2026):

- **El tema se busca en el TITULAR (`qInTitle`), no con `q`.** `q` busca
  también en el texto completo, que el plan gratuito no devuelve: de las 10
  noticias, sólo 1 («inteligencia artificial») y 4 («cambio climático»)
  nombraban el tema en el título o en la entradilla, y entre comillas salieron
  las mismas 10. Con `qInTitle`, 10 de 10 en los dos, a cambio de muchos menos
  resultados (226 frente a 4.211, y 25 frente a 762), que siguen sobrando para
  llenar los 10 (parte `busqueda` del spike). Para analizar titulares es lo
  que interesa: uno que nombre el tema.
- La misma noticia llega a veces repetida (una pareja en dos de esas seis
  búsquedas): se queda la primera de cada titular (`_sin_repetidos`).

- **No se puede elegir la ventana de fechas**: `timeframe` responde 422 en el
  plan gratuito («Access Denied! To use the timeframe parameter, please upgrade
  your plan…»), así que la herramienta no tiene `days`. Para ir más atrás está
  GNews.
- **`content` es una trampa**: llega en todas las noticias con el texto «ONLY
  AVAILABLE IN PAID PLANS». El cuerpo que se devuelve es `description` (56–3.271
  caracteres en lo medido), y `content` no se lee nunca.
- La fecha (`pubDate`) llega como «2026-10-08 21:51:12», con la zona aparte
  (`pubDateTZ`, siempre «UTC» en lo medido); se pasa a ISO 8601 como las demás
  fuentes (`_fecha_iso`).
- Lo más reciente tiene unas 12 horas, como en GNews.
- La cuota SÍ sale en las cabeceras: `x-api-limit-remaining` son los créditos
  del día que quedan (200 en el plan gratuito), y `x-ratelimit-limit` el tope
  de 60 peticiones cada 15 minutos (`retry-after` ~900 s). Un 422 no gastó
  crédito.
- Una clave que no existe da 401, y el cuerpo no la repite.

La clave es opcional (`settings.newsdata_api_key`): sin ella no se hace ninguna
petición, y el fallo dice qué falta. Como GNews, no tiene sonda en `/health`.
"""

from datetime import UTC, datetime

import httpx

from backend.config.settings import settings
from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult

SIN_CLAVE = (
    "NewsData.io no está configurado: falta NEWSDATA_API_KEY en la configuración."
)


def _fecha_iso(fecha: str | None, zona: str | None) -> str | None:
    """`pubDate` en ISO 8601, como las demás fuentes («2026-10-08T21:51:12Z»).

    Con otra zona que «UTC», o con otro formato, se devuelve tal cual: mejor
    una fecha en un formato raro que una mal convertida.
    """
    if not fecha or zona != "UTC":
        return fecha
    try:
        convertida = datetime.strptime(fecha, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return fecha
    return convertida.strftime("%Y-%m-%dT%H:%M:%SZ")


def _sin_repetidos(articulos: list[dict]) -> list[dict]:
    """La primera noticia de cada titular, en el orden en que llegaron.

    Las que no traen titular se quedan todas: no hay con qué compararlas. La
    misma regla está en el cliente de GNews.
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


class NewsDataAPI(BaseAPI):
    BASE_URL = "https://newsdata.io/api/1/"

    API_KEY = (
        settings.newsdata_api_key.get_secret_value()
        if settings.newsdata_api_key
        else None
    )
    API_KEY_PARAM = "apikey"

    # 60 peticiones cada 15 minutos, lo que publica `x-ratelimit-limit`.
    RATE_CALLS = 60
    RATE_PERIOD = 900

    async def latest_articles(self, topic: str | None = None) -> ToolResult:
        """Las últimas noticias en español de NewsData.io.

        Llama a `/latest` (https://newsdata.io/documentation).

        Args:
            topic (str, optional): palabras clave que deben estar en el
                titular. Si se omite, devuelve lo último publicado sin filtrar
                por tema. Defaults to None.

        Params enviados:
            - qInTitle: <topic> CONDICIONAL! (no `q`: ver arriba)
            - language: es

        Sin `size`: el defecto, 10, es el máximo del plan gratuito.

        Respuesta de llamada a endpoint (campos consumidos):
            results[].title        → title
            results[].link         → url
            results[].pubDate      → date (con `pubDateTZ`, en ISO 8601)
            results[].description  → content
            results[].source_name  → source (o `source_id` si falta)

        Returns:
            ToolResult.ok([{title, url, date, content, source}, ...]) si hay
                artículos, sin titulares repetidos.
            ToolResult.fail("No articles found") si `results` está vacío o ausente.
            ToolResult.fail(SIN_CLAVE) sin clave, sin llamar a la API.
            El error de `make_request`, tal cual, si la petición falla.
        """
        if not self.API_KEY:
            return ToolResult.fail(SIN_CLAVE)

        params = {"language": "es"}
        if topic:
            params["qInTitle"] = topic

        response = await self.make_request("latest", "get", params)

        # Un fallo NO es «no hay noticias» (#196, #212).
        if not response.success:
            return response

        if not response.has_content():
            return ToolResult.fail("No articles found")

        results = response.unwrap().get("results")

        if not results:
            return ToolResult.fail("No articles found")

        articles = [
            {
                "title": article.get("title"),
                "url": article.get("link"),
                "date": _fecha_iso(article.get("pubDate"), article.get("pubDateTZ")),
                # Nunca `content`: en el plan gratuito es un aviso, no el texto.
                "content": article.get("description"),
                "source": article.get("source_name") or article.get("source_id"),
            }
            for article in results
        ]

        return ToolResult.ok(_sin_repetidos(articles))

    # La cuota la publica la propia API: los créditos del día que quedan. Sólo
    # si son dígitos: se lee DENTRO de `make_request`, y un `int()` que fallara
    # convertiría en un fallo una petición que salió bien.
    def _read_quota(self, response: httpx.Response) -> None:
        restantes = response.headers.get("x-api-limit-remaining", "")
        self._remaining = int(restantes) if restantes.isdigit() else None
