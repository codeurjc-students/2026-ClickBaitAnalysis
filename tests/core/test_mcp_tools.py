"""Pruebas de `_leer` (`core/mcp/tools.py`): qué se publica de un fallo (#301).

Todo resultado de una herramienta pasa por `_leer` camino de la API y del
agente, así que es ahí donde se decide qué texto de un fallo puede salir (R12.7).
Los textos no se escriben a mano: los produce un FastMCP de verdad, en memoria,
porque lo que se prueba es la forma que les da la librería, y una forma escrita
a mano seguiría pasando aunque la librería cambiara la suya.
"""

from typing import NotRequired, TypedDict

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult
from structlog.testing import capture_logs

from backend.core.mcp.tools import _leer

SERVIDOR = "servidor-de-prueba"


class Salida(TypedDict):
    texto: str


class ConOpcional(TypedDict):
    texto: str
    nota: NotRequired[str]


def _servidor() -> FastMCP:
    """Un servidor con una herramienta que falla bien y dos cuya salida no
    cumple su propio esquema, cada una de una manera."""
    mcp = FastMCP(SERVIDOR)

    @mcp.tool()
    def rota() -> Salida:
        """Falla con una frase ya redactada para publicarse."""
        raise ToolError("La herramienta de prueba ha fallado a propósito.")

    @mcp.tool()
    def salida_que_no_encaja() -> Salida:
        """Devuelve una lista donde su modelo de salida pide un texto."""
        return {"texto": ["no", "es", "texto"]}  # pyright: ignore[reportReturnType]

    @mcp.tool()
    def salida_sin_su_opcional() -> ConOpcional:
        """Omite un campo `NotRequired`, que FastMCP escribe como `null` (#230)."""
        return {"texto": "hola"}

    return mcp


async def _llamar(nombre: str) -> CallToolResult:
    """Lo que recibe el cliente MCP, tal cual, antes de pasar por `_leer`."""
    async with create_connected_server_and_client_session(_servidor()) as sesion:
        return await sesion.call_tool(nombre, {})


@pytest.mark.asyncio
async def test_la_frase_de_una_herramienta_sale_sin_el_prefijo():
    """Lo que sí se publica: la frase de un `ToolError`, que la herramienta
    redacta para eso (#89), sin el «Error executing tool …» de FastMCP (#191).
    Vigila que el arreglo de #301 no se pase de largo."""
    invocacion = _leer(await _llamar("rota"), "rota", SERVIDOR)

    assert invocacion.result.error == "La herramienta de prueba ha fallado a propósito."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("nombre", "original"),
    [
        # Con el prefijo de FastMCP: Pydantic rechaza la salida con su modelo.
        ("salida_que_no_encaja", "1 validation error for Salida"),
        # Sin el prefijo: lo genera el servidor de bajo nivel, con `jsonschema`,
        # después de que la herramienta haya terminado.
        ("salida_sin_su_opcional", "Output validation error: None is not of type"),
        # Sin el prefijo, y de antes de llamar a nada.
        ("no_existe", "Unknown tool: no_existe"),
    ],
    ids=["salida-segun-pydantic", "salida-segun-jsonschema", "herramienta-que-no-hay"],
)
async def test_lo_que_no_redacto_la_herramienta_no_se_publica(nombre, original):
    """Hasta #301, `_leer` sólo quitaba el prefijo, y estos textos salían por
    `/tools/{name}/execute` y hacia el agente. Ahora sale la frase pública, y
    el original queda en el registro."""
    resultado = await _llamar(nombre)

    with capture_logs() as registrado:
        invocacion = _leer(resultado, nombre, SERVIDOR)

    assert invocacion.result.success is False
    publicado = invocacion.result.error
    assert publicado is not None
    assert original not in publicado
    assert "validation error" not in publicado
    assert "no previsto" in publicado
    (fallo,) = [
        linea for linea in registrado if linea["event"] == "tool.execute.failed"
    ]
    assert original in fallo["motivo"]


def test_un_fallo_sin_texto_no_se_inventa_un_motivo():
    """Un fallo sin contenido de texto salía como «Error desconocido», una frase
    que no decía dónde mirar. Ahora es la misma que cualquier otro fallo que
    no redactó la herramienta."""
    invocacion = _leer(CallToolResult(content=[], isError=True), "muda", SERVIDOR)

    assert invocacion.result.error is not None
    assert "no previsto" in invocacion.result.error
