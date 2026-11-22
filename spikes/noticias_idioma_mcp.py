"""#263 (2026-10-14) - Las cuatro herramientas de noticias, llamadas por FastMCP.

Las pruebas de cada cliente comprueban que cada noticia trae `language`, y las
de cada herramienta usan dobles que devuelven listas vacías. Este guion llama a
las cuatro por `call_tool`, como el agente, con las APIs simuladas con `respx`:
así se ve que su salida pasa el `outputSchema` que publica FastMCP, que desde
#263 exige `language`, y qué idioma trae cada noticia.

Sin red ni claves de verdad: pone una de prueba en cada cliente.

Ejecutar desde la raíz:
    .venv/bin/python spikes/noticias_idioma_mcp.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import respx  # noqa: E402
from httpx import Response  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

from backend.integrations.gnews import tool as gnews_tool  # noqa: E402
from backend.integrations.gnews.client import GNewsAPI  # noqa: E402
from backend.integrations.guardian import tool as guardian_tool  # noqa: E402
from backend.integrations.guardian.client import GuardianAPI  # noqa: E402
from backend.integrations.newsdata import tool as newsdata_tool  # noqa: E402
from backend.integrations.newsdata.client import NewsDataAPI  # noqa: E402
from backend.integrations.nyt import tool as nyt_tool  # noqa: E402
from backend.integrations.nyt.client import NYTAPI  # noqa: E402

for cliente in (GNewsAPI, NewsDataAPI, GuardianAPI, NYTAPI):
    cliente.API_KEY = "clave-de-prueba-263"


async def main() -> None:
    mcp = FastMCP("noticias-idioma")
    for herramienta in (gnews_tool, newsdata_tool, guardian_tool, nyt_tool):
        herramienta.register(mcp)

    # Una noticia por API, con la forma medida en #235 (GNews y NewsData traen
    # su propio idioma, que el cliente no lee) y en las pruebas de cada una.
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{GNewsAPI.BASE_URL}search").mock(
            return_value=Response(
                200, json={"articles": [{"title": "La IA resolvió el misterio", "lang": "es"}]}
            )
        )
        router.get(f"{NewsDataAPI.BASE_URL}latest").mock(
            return_value=Response(
                200, json={"results": [{"title": "WeatherNext 3", "language": "spanish"}]}
            )
        )
        # Sin etiqueta, Guardian busca el tema como texto libre (#196).
        router.get(f"{GuardianAPI.BASE_URL}tags").mock(
            return_value=Response(200, json={"response": {"results": []}})
        )
        router.get(f"{GuardianAPI.BASE_URL}search").mock(
            return_value=Response(
                200, json={"response": {"results": [{"webTitle": "A Guardian headline"}]}}
            )
        )
        router.get(f"{NYTAPI.BASE_URL}articlesearch.json").mock(
            return_value=Response(
                200, json={"response": {"docs": [{"headline": {"main": "A NYT headline"}}]}}
            )
        )

        resultados = []
        for nombre in ("get_gnews_news", "get_newsdata_news", "get_guardian_news", "get_nyt_news"):
            # FastMCP valida aquí la salida contra su `outputSchema`: si faltara
            # `language`, `call_tool` lanzaría en vez de devolver.
            _, estructurado = await mcp.call_tool(nombre, {"topic": "tema"})
            noticias = estructurado["result"]
            resultados.append(
                f"{nombre}: {[(noticia['title'], noticia['language']) for noticia in noticias]}"
            )

    print("\n".join(resultados))


asyncio.run(main())
