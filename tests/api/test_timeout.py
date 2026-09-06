"""Que un servidor MCP lento no cuelgue la petición.

Antes de esto, una herramienta que tardaba más que su timeout **no fallaba: se
colgaba para siempre**. Medido — la tool terminó en el servidor con éxito a los
151 s mientras la API llevaba seis minutos con la conexión abierta y 0 % de CPU.

Hay dos ficheros de test y prueban cosas distintas a propósito:

- **Éste**, rápido: sustituye la sesión por una que duerme, así que corre en
  milisegundos y entra en el CI. Prueba **la traducción** — que un timeout acaba
  en un 504 y no en un 500 ni en un `status: error`.
- **`tests/integration/test_timeout_real.py`**, marcado `integration`: levanta un
  servidor MCP de verdad con una tool lenta. Prueba **el mecanismo** — que
  `asyncio.timeout` corta donde el timeout de httpx no cortaba.

El rápido no vale por sí solo: si sustituyes la sesión, ya no estás probando la
capa que tenía el fallo. Y el fiel no puede ir en el CI porque tarda segundos por
escenario. Cada uno cubre lo que el otro no.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.api import app as app_mod
from backend.api.app import app
from backend.api.execute import execute_tool
from backend.core.mcp import tools as mcp_tools
from backend.core.mcp.tools import ToolNotFound, ToolTimeout

client = TestClient(app)


@pytest.fixture
def sesion_lenta(monkeypatch):
    """Una sesión MCP que tarda más de la cuenta, sin levantar nada.

    Reproduce la forma en que el fallo llega de verdad: el `TimeoutError` sale
    **envuelto en dos ExceptionGroup**, uno por cada task group de anyio
    (`streamable_http_client` y `ClientSession`). Es lo que hace que un
    `except TimeoutError` normal no lo capture.
    """

    def instalar(anidamiento: int = 2):
        async def falso_intentar(url, name, arguments, timeout):
            exc: BaseException = TimeoutError()
            for _ in range(anidamiento):
                exc = ExceptionGroup("unhandled errors in a TaskGroup", [exc])
            raise exc

        monkeypatch.setattr(mcp_tools, "_intentar", falso_intentar)

    return instalar


# ----- la traducción a HTTP -----


def test_un_timeout_devuelve_504(sesion_lenta):
    """504 y no 500: la petición era correcta, lo que falló fue la espera."""
    sesion_lenta()

    response = client.post("/tools/detect_clickbait/execute", json={"arguments": {}})

    assert response.status_code == 504


def test_el_504_dice_que_puede_seguir_ejecutandose(sesion_lenta):
    """El detalle importa porque el trabajo PUEDE haber salido bien: al agotarse
    la espera la herramienta sigue corriendo al otro lado. Decir «el análisis
    falló» sería mentir."""
    sesion_lenta()

    detalle = client.post(
        "/tools/detect_clickbait/execute", json={"arguments": {}}
    ).json()["detail"]

    assert "detect_clickbait" in detalle
    assert "ejecutándose" in detalle


def test_no_se_confunde_con_una_herramienta_que_falla(sesion_lenta):
    """Un timeout NO es un `status: error`. Aquel significa «se ejecutó y falló»
    y sale con 200; éste significa «dejamos de esperar» y sale con 504."""
    sesion_lenta()

    response = client.post("/tools/detect_clickbait/execute", json={"arguments": {}})

    assert response.status_code != 200
    assert "status" not in response.json()


# ----- el desenvuelto del ExceptionGroup -----


@pytest.mark.parametrize("capas", [0, 1, 2, 3])
def test_se_reconoce_a_cualquier_profundidad(sesion_lenta, capas):
    """`except*` compara por tipo a cualquier nivel del árbol, así que da igual
    cuántos task groups anidados ponga la librería. Hoy son dos; el test fija que
    seguirá funcionando si mañana son tres — o ninguno."""
    sesion_lenta(anidamiento=capas)

    with pytest.raises(ToolTimeout):
        asyncio.run(execute_tool("detect_clickbait", {}))


def test_otros_fallos_siguen_su_camino(monkeypatch):
    """El desenvuelto no puede tragarse cualquier cosa: un fallo que no sea de
    tiempo tiene que seguir subiendo tal cual."""

    async def revienta(url, name, arguments, timeout):
        raise ExceptionGroup(
            "unhandled errors in a TaskGroup", [ValueError("otra cosa")]
        )

    monkeypatch.setattr(mcp_tools, "_intentar", revienta)

    with pytest.raises(BaseExceptionGroup):
        asyncio.run(execute_tool("detect_clickbait", {}))


# ----- que no se rompió lo de antes -----


def test_las_otras_categorias_no_cambian(monkeypatch):
    """404 y 422 seguían funcionando; el 504 se añade, no sustituye."""

    async def no_existe(name, arguments):
        raise ToolNotFound(name)

    monkeypatch.setattr(app_mod, "execute_tool", no_existe)
    assert (
        client.post("/tools/inventada/execute", json={"arguments": {}}).status_code
        == 404
    )


def test_el_contrato_declara_los_tres_finales(monkeypatch):
    """Que ocurran no basta: tienen que estar PUBLICADOS (#129).

    El cliente de Angular se genera del contrato, así que un código que sólo
    vive en el `raise` obliga a leer `app.py`. Aquí son tres y significan cosas
    distintas: el 404 es que la herramienta no existe, el 422 que los argumentos
    no encajan en su esquema, y el 504 que se agotó la espera — que **no** es
    que la herramienta fallara: en #113 terminó bien a los 151 s con la API ya
    desistida.

    (El 200 con `status: error` no aparece aquí porque no es un final aparte:
    la petición fue correcta y la respuesta es un `ExecuteResponse` normal.)
    """
    respuestas = client.get("/openapi.json").json()["paths"]["/tools/{name}/execute"][
        "post"
    ]["responses"]

    assert {"404", "422", "504"} <= set(respuestas)
    assert "espera" in respuestas["504"]["description"]
