import pytest
import structlog
from mcp.server.fastmcp import FastMCP

from backend.api import ratelimit
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


@pytest.fixture(autouse=True)
def _sin_limite_de_velocidad(monkeypatch):
    """Apaga el limitador de #169 en TODA la suite, salvo donde se prueba.

    El presupuesto por defecto son 60 peticiones por minuto y por cliente, y
    para el `TestClient` todos los tests son **el mismo cliente**: un módulo que
    haga muchas peticiones empezaría a recibir 429 por un motivo que no tiene
    nada que ver con lo que prueba. Es la lección 1 de #158 con otro traje —un
    guardián puesto en medio secuestra pruebas ajenas—, y ahí costó cinco.

    Los de `tests/api/test_ratelimit.py` lo encienden con su propio presupuesto.
    Y el limitador se reinicia SIEMPRE, encendido o no: los contadores son
    estado de módulo, así que lo que gasta un test se lo encontraría el
    siguiente.
    """
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    ratelimit.reiniciar_limitador()
    yield
    ratelimit.reiniciar_limitador()


@pytest.fixture(autouse=True)
def _sondeo_de_salud_sin_cache(monkeypatch):
    """Quita la caché de `check_health` en toda la suite, salvo donde se prueba.

    Por lo mismo: es estado de módulo. Un test que sondea deja el resultado
    puesto, y el siguiente recibiría ESE en vez de lo que montó con `respx` —
    pasaría o fallaría sin llegar a ejercitar nada.
    """
    monkeypatch.setattr(settings, "health_cache_s", 0.0)
    health.olvidar_sondeo()
    yield
    health.olvidar_sondeo()


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
