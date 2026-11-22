import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from structlog.testing import capture_logs

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
    #
    # Desde #292 relanza un `ToolError` con una frase pública, y no el
    # `RuntimeError` tal cual: lo que publica, en la prueba siguiente.
    with pytest.raises(ToolError):
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


@pytest.mark.asyncio
async def test_un_error_imprevisto_no_publica_su_texto():
    """R12.7 (#292): lo que lanza una herramienta y no es un `ToolError` es un
    fallo que nadie redactó para publicarse. FastMCP lo envolvería en «Error
    executing tool …: <texto>», y ese texto saldría por `/tools/{name}/execute`
    y llegaría al modelo del agente: un `KeyError` cuenta cómo está hecho el
    código por dentro (#163). Sale la frase de `mensaje_publico`."""

    @log_tool_invocation
    async def herramienta_rota(state: str) -> str:
        raise KeyError("campo_secreto")

    with capture_logs() as registrado, pytest.raises(ToolError) as fallo:
        await herramienta_rota(state="CA")

    mensaje = str(fallo.value)
    assert mensaje.startswith("La herramienta ")
    assert "no previsto" in mensaje
    # Un test de una salida pública afirma lo que NO está en ella (#185).
    assert "campo_secreto" not in mensaje
    assert "KeyError" not in mensaje
    # Y lo que no se publica se registra: sanear sin registrar ciega la
    # depuración (#89).
    (fallo_registrado,) = registrado
    assert "KeyError: 'campo_secreto'" in fallo_registrado["exception"]


@pytest.mark.asyncio
async def test_un_tool_error_pasa_intacto():
    """Un `ToolError` lo lanza la herramienta a propósito, con una frase ya
    pensada para publicarse (#89): el decorador no la cambia."""
    deliberado = ToolError("El titular está vacío o no es válido")

    @log_tool_invocation
    async def herramienta(state: str) -> str:
        raise deliberado

    with capture_logs(), pytest.raises(ToolError) as fallo:
        await herramienta(state="CA")

    assert fallo.value is deliberado
