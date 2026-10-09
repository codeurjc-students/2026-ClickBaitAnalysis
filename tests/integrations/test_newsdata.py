"""Tests del cliente y la herramienta de NewsData.io (#235).

Sin red: `respx` hace de NewsData.io, con respuestas de la forma medida en
`spikes/noticias_es.py`. La clave es de prueba (`con_clave`): en el CI no hay
`NEWSDATA_API_KEY`. Los `integration` van contra la API real.
"""

import pytest
import respx
from httpx import Response
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from structlog.testing import capture_logs

from backend.core.models import ToolResult
from backend.integrations.newsdata import tool as newsdata_tool
from backend.integrations.newsdata.client import SIN_CLAVE, NewsDataAPI, _fecha_iso

CLAVE_DE_PRUEBA = "clave-newsdata-de-prueba-235"
ULTIMAS = f"{NewsDataAPI.BASE_URL}latest"


def noticia(titulo: str | None = "WeatherNext 3, el modelo de IA de Google") -> dict:
    """Una noticia con la forma que devuelve NewsData.io (medida el 9 oct 2026)."""
    return {
        "article_id": "a1b2c3",
        "title": titulo,
        "link": "https://www.ejemplo.com/tecnologia/weathernext",
        "description": "Google DeepMind ha desarrollado un modelo de previsión.",
        # Lo que llega SIEMPRE en el plan gratuito: un aviso, no el texto.
        "content": "ONLY AVAILABLE IN PAID PLANS",
        "pubDate": "2026-10-08 21:51:12",
        "pubDateTZ": "UTC",
        "source_id": "ambito",
        "source_name": "Ámbito",
        "language": "spanish",
        "country": ["argentina"],
        "keywords": ["inteligencia artificial"],
    }


def respuesta(*noticias: dict, cabeceras: dict | None = None) -> Response:
    return Response(
        200,
        json={
            "status": "success",
            "totalResults": len(noticias),
            "results": list(noticias),
        },
        headers=cabeceras,
    )


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setattr(NewsDataAPI, "API_KEY", CLAVE_DE_PRUEBA)


@pytest.mark.asyncio
async def test_extrae_los_campos_y_nunca_lee_content(con_clave):
    """`content` es «ONLY AVAILABLE IN PAID PLANS» en todas (medido): el cuerpo
    sale de `description`, y la fecha, a ISO 8601 como las demás fuentes."""
    esperada = noticia()
    with respx.mock:
        respx.get(ULTIMAS).mock(return_value=respuesta(esperada))
        result = await NewsDataAPI().latest_articles("inteligencia artificial")

    assert result.success
    assert len(result.data) == 1
    assert result.data[0]["title"] == esperada["title"]
    assert result.data[0]["url"] == esperada["link"]
    assert result.data[0]["date"] == "2026-10-08T21:51:12Z"
    assert result.data[0]["content"] == esperada["description"]
    assert result.data[0]["source"] == esperada["source_name"]


@pytest.mark.asyncio
async def test_sin_nombre_del_medio_usa_su_id(con_clave):
    sin_nombre = {**noticia(), "source_name": None}
    with respx.mock:
        respx.get(ULTIMAS).mock(return_value=respuesta(sin_nombre))
        result = await NewsDataAPI().latest_articles()

    assert result.data[0]["source"] == "ambito"


@pytest.mark.asyncio
async def test_con_tema_busca_en_el_titular(con_clave):
    """`qInTitle` y no `q`: `q` busca también en el texto completo, que el plan
    gratuito no da, y trajo 1 y 4 de 10 noticias del tema; `qInTitle`, 10 y 10
    (parte `busqueda` del spike)."""
    with respx.mock:
        ruta = respx.get(ULTIMAS).mock(return_value=respuesta(noticia()))
        await NewsDataAPI().latest_articles("inteligencia artificial")

    enviado = ruta.calls.last.request.url.params
    assert enviado["qInTitle"] == "inteligencia artificial"
    assert "q" not in enviado
    assert enviado["language"] == "es"
    assert enviado["apikey"] == CLAVE_DE_PRUEBA
    # Ni país (noticias en español, no de un país) ni ventana de fechas, que
    # en el plan gratuito da 422 (medido).
    assert "country" not in enviado
    assert "timeframe" not in enviado


@pytest.mark.asyncio
async def test_sin_tema_no_filtra(con_clave):
    with respx.mock:
        ruta = respx.get(ULTIMAS).mock(return_value=respuesta(noticia()))
        result = await NewsDataAPI().latest_articles()

    assert result.success
    enviado = ruta.calls.last.request.url.params
    assert "qInTitle" not in enviado
    assert "q" not in enviado


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cuerpo",
    [{"status": "success", "totalResults": 0, "results": []}, {"status": "success"}],
)
async def test_sin_noticias(con_clave, cuerpo):
    with respx.mock:
        respx.get(ULTIMAS).mock(return_value=Response(200, json=cuerpo))
        result = await NewsDataAPI().latest_articles("nadaquecoincidaabcde")

    assert not result.success
    assert result.error == "No articles found"


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", [401, 422, 429, 500])
async def test_un_fallo_de_la_api_no_se_disfraza_de_sin_noticias(con_clave, estado):
    """Como NYT (#212) y Guardian (#196). 401 es una clave que no existe y 422
    un parámetro que el plan no admite (los dos, medidos); 429, la cuota."""
    with respx.mock:
        respx.get(ULTIMAS).mock(
            return_value=Response(estado, json={"status": "error", "results": {}})
        )
        result = await NewsDataAPI().latest_articles("elecciones")

    assert not result.success
    assert "No articles found" not in result.error
    assert str(estado) in result.error


@pytest.mark.asyncio
async def test_el_error_publicado_no_lleva_la_clave_ni_la_url(con_clave):
    """El error es una salida pública (#163)."""
    with respx.mock:
        respx.get(ULTIMAS).mock(
            return_value=Response(401, text=f"Invalid key: {CLAVE_DE_PRUEBA}")
        )
        result = await NewsDataAPI().latest_articles("elecciones")

    assert not result.success
    assert CLAVE_DE_PRUEBA not in result.error
    assert "newsdata.io" not in result.error


@pytest.mark.asyncio
async def test_sin_clave_no_pide_nada_y_dice_que_falta(monkeypatch):
    monkeypatch.setattr(NewsDataAPI, "API_KEY", None)
    with respx.mock(assert_all_called=False):
        ruta = respx.get(ULTIMAS)
        result = await NewsDataAPI().latest_articles("elecciones")

    assert not ruta.called
    assert not result.success
    assert result.error == SIN_CLAVE
    assert "NEWSDATA_API_KEY" in result.error


@pytest.mark.asyncio
async def test_quita_los_titulares_repetidos(con_clave):
    """La misma noticia llega a veces dos veces (medido): se queda la primera.
    Las que no traen titular no se comparan, y se quedan todas."""
    repetida = noticia("Medio millón de pingüinos desaparecen")
    otra = noticia("Lesaka estudiará sus bosques ante el cambio climático")
    sin_titular = noticia(None)
    with respx.mock:
        respx.get(ULTIMAS).mock(
            return_value=respuesta(repetida, otra, repetida, sin_titular, sin_titular)
        )
        result = await NewsDataAPI().latest_articles("cambio climático")

    assert [articulo["title"] for articulo in result.data] == [
        "Medio millón de pingüinos desaparecen",
        "Lesaka estudiará sus bosques ante el cambio climático",
        None,
        None,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cabeceras", "restantes"),
    [
        ({"x-api-limit-remaining": "187"}, 187),
        ({"x-api-limit-remaining": "unlimited"}, None),
        ({}, None),
    ],
)
async def test_la_cuota_restante_sale_de_la_cabecera(con_clave, cabeceras, restantes):
    """NewsData.io publica los créditos del día que quedan (medido). Una cabecera
    rara no puede convertir en un fallo una petición que salió bien."""
    with respx.mock:
        respx.get(ULTIMAS).mock(return_value=respuesta(noticia(), cabeceras=cabeceras))
        api = NewsDataAPI()
        result = await api.latest_articles("elecciones")

    assert result.success
    assert api.remaining_quota == restantes


@pytest.mark.parametrize(
    ("fecha", "zona", "esperada"),
    [
        ("2026-10-08 21:51:12", "UTC", "2026-10-08T21:51:12Z"),
        # Con otra zona o con otro formato, tal cual: mejor una fecha en un
        # formato raro que una mal convertida.
        ("2026-10-08 21:51:12", "CET", "2026-10-08 21:51:12"),
        ("8/10/2026", "UTC", "8/10/2026"),
        (None, "UTC", None),
    ],
)
def test_la_fecha_pasa_a_iso_solo_si_es_la_medida(fecha, zona, esperada):
    assert _fecha_iso(fecha, zona) == esperada


@pytest.mark.asyncio
async def test_un_tema_que_solo_dice_none_es_buscar_sin_tema(monkeypatch):
    """#197, como en NYT y Guardian."""
    recibido = []

    async def buscar(self, topic=None):
        recibido.append(topic)
        return ToolResult.ok([])

    monkeypatch.setattr(NewsDataAPI, "latest_articles", buscar)
    mcp = FastMCP("test")
    newsdata_tool.register(mcp)

    await mcp.call_tool("get_newsdata_news", {"topic": "None"})

    assert recibido == [None]


@pytest.mark.asyncio
async def test_la_herramienta_sin_clave_dice_que_falta(monkeypatch):
    monkeypatch.setattr(NewsDataAPI, "API_KEY", None)
    mcp = FastMCP("test")
    newsdata_tool.register(mcp)

    # `capture_logs`: el decorador de la herramienta registra el fallo con su
    # traza, y con la configuración de structlog por defecto eso avisa.
    with capture_logs(), pytest.raises(ToolError, match="NEWSDATA_API_KEY"):
        await mcp.call_tool("get_newsdata_news", {"topic": "elecciones"})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_una_clave_mala_da_el_error_real(monkeypatch):
    """Contra la API real: a una clave que no existe NewsData.io responde 401
    (medido el 9 oct 2026). La clave tampoco puede salir."""
    monkeypatch.setattr(NewsDataAPI, "API_KEY", "clave-que-no-existe-235")
    result = await NewsDataAPI().latest_articles("elecciones")

    assert not result.success
    assert "No articles found" not in result.error, result.error
    assert "401" in result.error
    assert "clave-que-no-existe-235" not in result.error


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(NewsDataAPI.API_KEY is None, reason="sin NEWSDATA_API_KEY")
async def test_trae_noticias_en_espanol():
    """Gasta uno de los 200 créditos del día."""
    result = await NewsDataAPI().latest_articles("inteligencia artificial")

    assert result.success, result.error
    assert result.data[0]["title"]
    assert result.data[0]["url"]
    assert "ONLY AVAILABLE" not in (result.data[0]["content"] or "")
