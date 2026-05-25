import json

import structlog

from backend.core.logging import configure_logging


def test_logger_emits_structured_output_with_kwargs(monkeypatch, capsys):
    # monkeypatch = modificar cosas temporalmente durante un test
    # capsys = Captura lo que se escribe a sys.stdout y sys.stderr y se lee con readouterr()
    monkeypatch.setattr("backend.config.settings.settings.log_format", "json")
    configure_logging()

    log = structlog.get_logger()
    log.info("test", key="value")

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["event"] == "test"
    assert payload["key"] == "value"
    assert payload["level"] == "info"
    assert "timestamp" in payload
