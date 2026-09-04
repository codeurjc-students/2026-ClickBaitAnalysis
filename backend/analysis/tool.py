"""Expone la orquestación como herramienta MCP.

**Por qué existe este fichero**: sin él, el servidor MCP ofrece las cinco señales
sueltas y nada que las contraste. Un agente conversacional obtendría los
resultados crudos y tendría que combinarlos él — que es justo el veredicto de
caja negra que el proyecto rechaza, y además haría que el chat y el formulario
dieran respuestas distintas al mismo titular.

Con esta tool, **las dos fachadas comparten el mismo veredicto**: la REST llama a
`analyze` importándola, la MCP la llama por el protocolo, y en medio hay una sola
implementación de la jerarquía de dimensiones.

**Por qué se registra aquí y no en `integrations/nlp/tool.py`**: sería un ciclo.
`analysis/` importa las señales de `integrations/nlp/`, así que si el registro
viviera allí, `nlp` tendría que importar `analysis` de vuelta. Registrándolo en su
propio paquete la dependencia sigue yendo en un solo sentido.

Eso obliga a que `main.py` lo llame explícitamente, porque `discover_and_register`
sólo recorre `integrations/`. No es una excepción incómoda sino el patrón
declarado: **el descubrimiento encuentra las integraciones; lo que no es una
integración —la salud, el análisis— se registra a mano.** Ya era así para
`health.register(mcp)`.
"""

from mcp.server.fastmcp import FastMCP

from backend.analysis.domain import AnalyzeRequest, AnalyzeResponse
from backend.analysis.orchestrator import analyze
from backend.core.observability import log_tool_invocation
from backend.integrations.metadata import tool_meta


def register(mcp: FastMCP):
    # `integration` sale None, igual que en health_check: vive fuera de
    # `integrations/` y no envuelve ninguna fuente externa.
    #
    # La categoría NO es «Señales de análisis»: esta herramienta no es una señal
    # más, es la que las contrasta. Mezclarla con las cinco invitaría al modelo a
    # elegir entre ellas como si fueran alternativas del mismo tipo.
    @mcp.tool(meta=tool_meta("Análisis completo", __name__))
    @log_tool_invocation
    async def analyze_headline(
        headline: str, content: str | None = None
    ) -> AnalyzeResponse:
        """Analiza un titular contrastando TODAS las señales disponibles.

        Úsala cuando se pida un veredicto sobre un titular. Ejecuta las cinco
        señales, las agrupa por lo que miden —forma, engaño y tono— y declara las
        discrepancias en vez de promediarlas.

        Prefiérela a invocar las señales por separado: éstas devuelven cada una su
        propia medida, y combinarlas es lo que hace esta herramienta con una
        jerarquía explícita (el engaño pesa más que la forma).

        Args:
            headline: El titular a analizar, en inglés.
            content: Cuerpo o teaser de la noticia. Opcional; sin él no se puede
                evaluar la dimensión de engaño y esa señal queda como
                `not_applicable`.

        Returns:
            El veredicto global, el resultado de cada señal con su naturaleza
            (interpretable, híbrida u opaca) y el veredicto por dimensión.
        """
        return await analyze(AnalyzeRequest(headline=headline, content=content))
