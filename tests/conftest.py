import pytest
import structlog

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
