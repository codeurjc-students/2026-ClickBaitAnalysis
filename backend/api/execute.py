"""Ejecución de una herramienta concreta — ``POST /tools/{name}/execute``.

Sus dos consumidores son ejecutar **una señal suelta** —sólo el sentimiento, sin
lanzar las cuatro— y **traer una noticia** desde la pantalla de análisis. No un
catálogo que haga de lanzador.

Desde #137 aquí sólo queda la **traducción**: localizar, validar e invocar vive
en ``core/mcp/tools.py``, porque el agente de R13 necesita ese mecanismo y no
puede importarlo de una fachada. Lo que se queda es lo que sólo tiene sentido
por HTTP — los cuatro finales y su código de estado.

**Cuatro finales, cuatro categorías distintas:**

- La herramienta no existe → **404**. La petición pide algo que no hay.
- Los argumentos no encajan en su esquema → **422**. La petición está mal
  formada.
- La herramienta se ejecuta y falla → **200 con ``status`` en ``error``**. La
  petición era correcta y el servidor la atendió; lo que falló es el análisis.
  Mismo criterio que en ``/analyze``, donde una señal caída no tumba la
  respuesta.
- El servidor tarda más de la cuenta → **504**. Ver ``ToolTimeout``.

Los tres primeros los distingue quien llama por el tipo de excepción; el cuarto
llega como un resultado fallido. Esa separación es del mecanismo, no de aquí:
una excepción interrumpe, un resultado fallido es una respuesta.
"""

from backend.api.schemas import ExecuteResponse, ExecuteStatus
from backend.config.settings import settings
from backend.core.mcp import tools


async def execute_tool(name: str, arguments: dict) -> ExecuteResponse:
    """Invoca la herramienta y traduce el resultado al contrato de la API.

    Es quien **lee la configuración y la pasa**: el mecanismo recibe los
    servidores y el corte por parámetro para poder probarse sin montar un
    entorno. Aquí se usa ``mcp_execute_timeout`` y no ``mcp_timeout`` porque
    ejecutar necesita mucho más margen que descubrir — una señal NLP puede tener
    que cargar su modelo la primera vez.
    """
    invocacion = await tools.execute_tool(
        name,
        arguments,
        servers=settings.mcp_servers,
        timeout=settings.mcp_execute_timeout,
    )
    return _envolver(invocacion, name)


def _envolver(invocacion: tools.Invocation, name: str) -> ExecuteResponse:
    """Traduce el resultado neutro al contrato del endpoint."""
    if not invocacion.result.success:
        return ExecuteResponse(
            tool=name,
            server=invocacion.server,
            status=ExecuteStatus.ERROR,
            detail=invocacion.result.error,
        )

    return ExecuteResponse(
        tool=name,
        server=invocacion.server,
        status=ExecuteStatus.OK,
        data=invocacion.result.data,
    )
