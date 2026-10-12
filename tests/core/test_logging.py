import json

import structlog
from pydantic import SecretStr
from structlog.testing import capture_logs

from backend.config.settings import settings
from backend.core.logging import avisar_si_faltan_claves, configure_logging


def test_logger_emits_structured_output_with_kwargs(monkeypatch, capsys):
    # monkeypatch = modificar cosas temporalmente durante un test
    # capsys = Captura lo que se escribe a sys.stdout y sys.stderr y se lee con readouterr()
    monkeypatch.setattr("backend.config.settings.settings.log_format", "json")
    configure_logging()

    log = structlog.get_logger()
    log.info("test", key="value")

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert payload["event"] == "test"
    assert payload["key"] == "value"
    assert payload["level"] == "info"
    assert "timestamp" in payload


def _con_claves(monkeypatch, **claves: SecretStr | None) -> None:
    """Las cinco claves con un valor de prueba, salvo las que se pasan."""
    for campo in ("guardian_api_key", "nyt_api_key", "hf_token", "gnews_api_key", "newsdata_api_key"):
        monkeypatch.setattr(settings, campo, claves.get(campo, SecretStr("clave-de-prueba-259")))


def test_el_arranque_avisa_de_las_claves_que_faltan(monkeypatch):
    """#259: sin claves el proceso arranca, que es lo que se quería, pero quien
    despliega tiene que verlo en el registro: es lo que hacía visible fallar al
    arrancar. Una vacía cuenta como ausente, que es como llega de un
    `.env.example` copiado tal cual. El valor de una clave nunca sale."""
    _con_claves(monkeypatch, guardian_api_key=None, nyt_api_key=SecretStr(""))

    with capture_logs() as registro:
        avisar_si_faltan_claves()

    assert registro == [
        {
            "event": "configuracion.claves_sin_configurar",
            "log_level": "warning",
            "claves": ["GUARDIAN_API_KEY", "NYT_API_KEY"],
        }
    ]


def test_con_todas_las_claves_no_avisa(monkeypatch):
    _con_claves(monkeypatch)

    with capture_logs() as registro:
        avisar_si_faltan_claves()

    assert registro == []
