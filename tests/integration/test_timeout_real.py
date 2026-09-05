"""El corte por timeout, contra un servidor MCP de verdad.

Marcado `integration` porque **levanta un servidor y espera de verdad**: cada
escenario tarda segundos, así que no entra en el CI. Se lanza a mano:

    .venv/bin/python -m pytest tests/integration/test_timeout_real.py -m integration -v

Prueba lo que `tests/api/test_timeout.py` NO puede probar. Aquel sustituye la
sesión por una que lanza el error ya fabricado, así que verifica la traducción a
504 pero **no el mecanismo**: si `asyncio.timeout` no cortara, el test rápido
seguiría pasando igual.

Aquí no se fabrica nada. La tool duerme más que el timeout y se comprueba que la
llamada TERMINA, que era exactamente lo que no ocurría: el `timeout` de httpx
mide inactividad entre bytes y no duración, así que con una tool lenta no saltaba
y la petición se quedaba colgada para siempre.
"""

import asyncio
import sys
import time
from typing import TypedDict

import pytest
from mcp.server.fastmcp import FastMCP

from backend.api.execute import execute_tool
from backend.config.settings import settings
from backend.core.mcp.tools import ToolTimeout

pytestmark = pytest.mark.integration

PUERTO = 8799
URL = f"http://127.0.0.1:{PUERTO}/mcp"

TIMEOUT = 2.0  # lo que se le concede al cliente
DORMIR = 10.0  # lo que tarda la tool: cinco veces más
GUARDIA = 25.0  # si se pasa de aquí, es que sigue colgándose


class Tardanza(TypedDict):
    dormidos: float


def _construir_servidor() -> FastMCP:
    mcp = FastMCP("test-lento")
    mcp.settings.host = "127.0.0.1"
    mcp.settings.port = PUERTO

    @mcp.tool()
    async def dormir(segundos: float) -> Tardanza:
        """Duerme sin bloquear el bucle de eventos del servidor."""
        await asyncio.sleep(segundos)
        return {"dormidos": segundos}

    return mcp


@pytest.fixture(scope="module")
def servidor_lento():
    """Levanta el servidor en un proceso aparte y espera a que escuche.

    En un proceso y no en un hilo porque `mcp.run()` monta su propio bucle de
    eventos, y compartirlo con el del test es pedir problemas.
    """
    import subprocess

    guion = (
        "import sys; sys.path.insert(0, '.'); "
        "from tests.integration.test_timeout_real import _construir_servidor; "
        "_construir_servidor().run(transport='streamable-http')"
    )
    proceso = subprocess.Popen(
        [sys.executable, "-c", guion],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    limite = time.time() + 30
    while time.time() < limite:
        import socket

        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", PUERTO)) == 0:
                break
        time.sleep(0.3)
    else:
        proceso.kill()
        pytest.fail("el servidor de prueba no llegó a escuchar")

    yield
    proceso.kill()
    proceso.wait(timeout=10)


@pytest.fixture
def apuntando_al_lento(monkeypatch, servidor_lento):
    monkeypatch.setattr(settings, "mcp_servers", [URL])
    monkeypatch.setattr(settings, "mcp_execute_timeout", TIMEOUT)
    monkeypatch.setattr(settings, "mcp_timeout", TIMEOUT)


def test_una_tool_lenta_corta_en_vez_de_colgarse(apuntando_al_lento):
    """EL test de este issue. Antes del arreglo, esta llamada no volvía nunca.

    La cota es generosa a propósito: al agotarse el corte, cerrar la sesión aún
    necesita que el servidor conteste, así que el total supera el timeout pedido
    —medido: 2,1 s con el bucle del servidor libre, 4,0 s con él bloqueado—. Lo
    que importa es que esté ACOTADO, no que sea exacto.
    """

    async def llamar():
        return await execute_tool("dormir", {"segundos": DORMIR})

    t0 = time.perf_counter()
    with pytest.raises(ToolTimeout):
        asyncio.run(asyncio.wait_for(llamar(), timeout=GUARDIA))
    transcurrido = time.perf_counter() - t0

    assert transcurrido < GUARDIA - 1, "siguió colgándose hasta el vigilante"
    assert transcurrido >= TIMEOUT, "cortó antes de tiempo"


def test_una_tool_rapida_sigue_respondiendo(apuntando_al_lento):
    """El corte no puede haberse llevado por delante el camino normal."""

    async def llamar():
        return await execute_tool("dormir", {"segundos": 0.1})

    respuesta = asyncio.run(asyncio.wait_for(llamar(), timeout=GUARDIA))

    assert respuesta.status.value == "ok"
    assert respuesta.data == {"dormidos": 0.1}
