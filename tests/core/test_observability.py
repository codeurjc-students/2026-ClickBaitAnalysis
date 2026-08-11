import json

import pytest

from backend.core.logging import configure_logging
from backend.core.observability import log_tool_invocation


@pytest.mark.asyncio
async def test_log_tool_invocation_logs_success(monkeypatch, capsys):
    monkeypatch.setattr("backend.config.settings.settings.log_format", "json")
    configure_logging()

    @log_tool_invocation
    async def fake_tool(state: str) -> str:
        return f"alerts for {state}"

    result = await fake_tool(state="CA")

    assert result == "alerts for CA"

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert payload["event"] == "tool.invoke"
    assert payload["tool"] == "fake_tool"
    assert payload["params"] == {"kwargs": {"state": "CA"}}
    assert payload["success"] is True
    assert payload["level"] == "info"
    assert isinstance(payload["duration_ms"], (int, float))
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_log_tool_invocation_logs_failure(monkeypatch, capsys):
    monkeypatch.setattr("backend.config.settings.settings.log_format", "json")
    configure_logging()

    @log_tool_invocation
    async def failing_tool(state: str) -> str:
        raise RuntimeError("boom")

    # El decorador RELANZA: observar no es decidir qué se responde. Antes
    # devolvía "Internal error while executing tool", y esa cadena impedía que
    # la excepción llegara a MCP — el protocolo la tomaba por un resultado
    # válido (`isError` a False) y el fallo era indistinguible de un éxito.
    with pytest.raises(RuntimeError, match="boom"):
        await failing_tool(state="CA")

    captured = capsys.readouterr()

    payload = json.loads(captured.err)
    # print(payload)
    assert payload["event"] == "tool.invoke.failed"
    assert payload["tool"] == "failing_tool"
    assert payload["params"] == {"kwargs": {"state": "CA"}}
    assert payload["success"] is False
    assert payload["level"] == "error"
    assert (
        "RuntimeError: boom" in payload["exception"]
    )  # Campo exception explicitamente creado ya que log. exception = log.error"",exc_info=True

    # Ya tenemos nuestro binario success
    assert "timestamp" in payload
