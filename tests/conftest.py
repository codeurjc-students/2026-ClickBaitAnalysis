import json

import pytest
import structlog
from mcp.server.fastmcp import FastMCP

from backend.analysis import tool as analysis_tool
from backend.api import chat, ratelimit
from backend.config.settings import settings
from backend.core import health
from backend.integrations.discovery import discover_and_register
from backend.integrations.llm import factory as llm_factory
from backend.integrations.llm import grabado


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


@pytest.fixture(autouse=True)
def _sin_conversaciones_de_otro_test():
    """Vacía las conversaciones del asistente (#189) antes y después de cada test.

    También son estado de módulo, y con más motivo: el almacén lleva un
    semáforo, que se ata al bucle de eventos del primer test que lo usa y
    fallaría en el siguiente, que corre en otro.
    """
    chat.reiniciar_trabajos()
    yield
    chat.reiniciar_trabajos()


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
    y no una maqueta: descubrimiento de integraciones, el chequeo de salud y el
    análisis completo. Hasta #269 faltaba este último —13 herramientas de 14—,
    y ninguna prueba que usara la fixture veía `analyze_headline`.
    """
    mcp = FastMCP("tfg-mcp-server")
    discover_and_register(mcp)
    health.register(mcp)
    analysis_tool.register(mcp)
    return mcp


@pytest.fixture
def grabacion_de_prueba(tmp_path, monkeypatch):
    """El asistente configurado con respuestas grabadas (#265), y la grabación
    en una carpeta temporal: las pruebas no escriben en `grabaciones/`.

    La factoría guarda un reproductor por nombre de grabación, que lee su
    fichero una sola vez: sin vaciar esa caché, una prueba recibiría el de la
    anterior, con su carpeta ya borrada.
    """
    grabacion = {
        "model": "qwen3.5:27b",
        "model_digest": "7653528ba5cb",
        "recorded_at": "2026-11-13",
        "commit": "abc1234",
        "prompt": {"name": "06-dato", "text": "Eres el asistente de prueba."},
        "takes": {"recorded": 3, "chosen": 1},
        "conditions": {},
        "turns": [
            {
                "query": "Analiza el titular 'You Won't Believe This'",
                "rounds": [
                    {
                        "tool_results": [],
                        "response": {
                            "content": "Sin herramientas.",
                            "tool_calls": [],
                            "metrics": {
                                "prompt_tokens": 3100,
                                "output_tokens": 12,
                                "load_s": 0.1,
                                "total_s": 2.0,
                            },
                            "cortada": False,
                        },
                    }
                ],
            }
        ],
    }
    carpeta = tmp_path / "grabaciones"
    carpeta.mkdir()
    (carpeta / "prueba.json").write_text(
        json.dumps(grabacion, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(grabado, "CARPETA", carpeta)
    monkeypatch.setattr(settings, "llm_backend", "grabado")
    monkeypatch.setattr(settings, "llm_grabacion", "prueba")
    llm_factory._grabado_para.cache_clear()
    yield grabacion
    llm_factory._grabado_para.cache_clear()


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
