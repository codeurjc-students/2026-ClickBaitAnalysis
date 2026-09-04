"""La orquestación, expuesta como herramienta MCP.

Lo que se fija aquí no es que la tool «funcione» —eso ya lo cubre
`test_analyze.py` sobre la orquestación— sino **que el agente pueda llegar a
ella**: que esté registrada, que declare su contrato y que no se confunda con las
señales sueltas.

Es lo que impedía que el chat reprodujera el veredicto del formulario (#107).
"""

import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

from backend.analysis import orchestrator
from backend.analysis import tool as analysis_tool
from backend.analysis.domain import AnalyzeRequest, AnalyzeResponse, OverallVerdict


@pytest.fixture
def tool():
    """La herramienta ya resuelta, sobre un FastMCP con SÓLO ella dentro.

    Sin `discover_and_register`: lo que se prueba es que este paquete se registra
    por su cuenta, no que el descubrimiento lo encuentre — de hecho no puede,
    porque sólo recorre `integrations/`.
    """
    mcp = FastMCP("test")
    analysis_tool.register(mcp)

    async def buscar():
        return next(t for t in await mcp.list_tools() if t.name == "analyze_headline")

    return asyncio.run(buscar())


def test_la_orquestacion_se_expone_como_herramienta(tool):
    """El punto entero de #107: sin esto el servidor MCP ofrece las cinco señales
    sueltas y nada que las contraste, así que un agente no puede reproducir el
    veredicto del formulario."""
    assert tool.name == "analyze_headline"


def test_declara_su_contrato_de_salida(tool):
    """MCP sólo publica `outputSchema` si el tipo de retorno está DECLARADO — con
    `-> dict` no publica nada (#100). Aquí se devuelve un modelo Pydantic, que
    además resuelve los tipos anidados en `$defs`: el LLM ve los valores
    admitidos de cada enum, no sólo que hay un campo llamado `verdict`."""
    assert tool.outputSchema is not None
    assert set(tool.outputSchema["properties"]) == {
        "headline",
        "content",
        "signals",
        "dimensions",
        "verdict",
    }
    # Los tipos anidados llegan resueltos, no como referencias opacas.
    assert "OverallVerdict" in tool.outputSchema["$defs"]
    admitidos = tool.outputSchema["$defs"]["OverallVerdict"]["enum"]
    assert set(admitidos) == {v.value for v in OverallVerdict}


def test_no_se_presenta_como_una_senal_mas(tool):
    """Categoría propia a propósito. Mezclarla con «Señales de análisis»
    invitaría al modelo a elegir entre ella y las cinco como si fueran
    alternativas del mismo tipo, cuando es la que las contrasta."""
    assert tool.meta["category"] == "Análisis completo"
    # `integration` a None: vive fuera de `integrations/` y no envuelve nada
    # externo, igual que health_check.
    assert tool.meta["integration"] is None


def test_el_cuerpo_es_opcional(tool):
    """Sin cuerpo no se puede evaluar el engaño, pero el análisis sigue siendo
    válido: la señal queda en `not_applicable` y las demás votan igual."""
    requeridos = tool.inputSchema.get("required", [])
    assert "headline" in requeridos
    assert "content" not in requeridos


def test_las_dos_fachadas_comparten_implementacion():
    """La garantía de fondo: que no haya dos jerarquías de veredicto capaces de
    divergir. La tool no reimplementa nada — llama a la misma función que
    `/analyze` y devuelve el mismo tipo."""
    assert analysis_tool.analyze is orchestrator.analyze
    assert (
        AnalyzeRequest.__module__
        == AnalyzeResponse.__module__
        == "backend.analysis.domain"
    )
