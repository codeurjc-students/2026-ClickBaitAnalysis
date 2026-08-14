import pytest
import structlog
from mcp.server.fastmcp import FastMCP

from backend.config.settings import settings
from backend.core import health
from backend.integrations.discovery import discover_and_register


@pytest.fixture(autouse=True)
def _historial_aislado(tmp_path, monkeypatch):
    """Manda el historial a un fichero temporal, en TODOS los tests.

    Desde que `/analyze` registra cada análisis, los tests de la capa HTTP
    escriben en el historial de verdad: una sola corrida de la suite dejaba
    cuatro entradas «Un titular» en `var/history.db`, el fichero del usuario.

    Va aquí y con `autouse` —y no en el fichero que prueba el historial— porque
    quien contamina no es quien lo prueba: lo hace cualquier test que llame a un
    endpoint que registre, y eso incluye a los que aún no existen. Como
    `_ruta_db()` lee `settings` en cada llamada, basta con mover el ajuste.
    """
    monkeypatch.setattr(settings, "history_db", str(tmp_path / "history.db"))


@pytest.fixture
def servidor_mcp() -> FastMCP:
    """Un servidor MCP recién construido, con las mismas tools que `main.py`.

    NO se reutiliza `backend.main.mcp`, que es un singleton de módulo, porque
    `StreamableHTTPSessionManager.run()` **sólo puede llamarse una vez por
    instancia**: el primer test que levantara su app dejaría el gestor gastado y
    los siguientes fallarían con «can only be called once per instance» — un
    fallo que además depende del orden de ejecución, así que aparece y
    desaparece según qué tests se corran juntos.

    Se monta igual que `main.py` para que lo que se prueba sea el servidor real
    y no una maqueta: descubrimiento de integraciones más el chequeo de salud.
    """
    mcp = FastMCP("tfg-mcp-server")
    discover_and_register(mcp)
    health.register(mcp)
    return mcp


# Encontrado fallo de aislamiento entre tests al usar capsys.


# Autouse =  corre en todos los tests sin pedirlo.
@pytest.fixture(autouse=True)
def _reset_structlog():
    """Aísla la configuración GLOBAL de structlog entre tests.

    `configure_logging()` (usado por test_logging.py) muta el estado global de
    structlog y lo deja apuntando al stderr temporal de `capsys`, que se cierra
    al terminar el test. Sin este reset, el siguiente test que emita un log
    (p.ej. el evento `api.call` de BaseAPI.make_request) escribiría a un fichero
    ya cerrado -> ValueError: I/O operation on closed file.

    Restaurar los defaults tras cada test garantiza el aislamiento.
    """
    yield
    # Regresa control a test hasta que termina, donde vuelve aqui y cierra. Try: corre test. Finally Reset_defaults
    structlog.reset_defaults()
