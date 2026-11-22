"""Ejecución de una herramienta concreta — ``POST /tools/{name}/execute``.

Su consumidor es la pantalla de Sistema, que ejecuta desde el catálogo cualquier
herramienta con su formulario: **una señal suelta** —sólo el sentimiento, sin
lanzar las cuatro— o una fuente de noticias. No un catálogo que haga de
lanzador. *(Se pensó también para traer una noticia desde la pantalla de
análisis, y eso no llegó a hacerse: corregido en #216 en R4.3.)*

Desde #137 aquí sólo queda la **traducción**: localizar, validar e invocar vive
en ``core/mcp/tools.py``, porque el agente de R13 necesita ese mecanismo y no
puede importarlo de una fachada. Lo que se queda es lo que sólo tiene sentido
por HTTP — los cinco finales y su código de estado.

**Cinco finales, cinco categorías distintas:**

- La herramienta no existe → **404**. La petición pide algo que no hay.
- Los argumentos no encajan en su esquema → **422**. La petición está mal
  formada.
- La herramienta se ejecuta y falla → **200 con ``status`` en ``error``**. La
  petición era correcta y el servidor la atendió; lo que falló es el análisis.
  Mismo criterio que en ``/analyze``, donde una señal caída no tumba la
  respuesta.
- El servidor que la podría tener no responde → **503** (#292). Ver
  ``ServerUnavailable``.
- El servidor tarda más de la cuenta → **504**. Ver ``ToolTimeout``.

El 200 con error llega como un resultado fallido; los demás los distingue quien
llama por el tipo de excepción. Esa separación es del mecanismo, no de aquí:
una excepción interrumpe, un resultado fallido es una respuesta.

La respuesta lleva los argumentos con que se ejecutó (R9.2, #292): el historial
la guarda entera, y así queda qué se pidió.
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
    return _envolver(invocacion, name, arguments)


def _envolver(
    invocacion: tools.Invocation, name: str, arguments: dict
) -> ExecuteResponse:
    """Traduce el resultado neutro al contrato del endpoint.

    Los argumentos van también cuando falla, que es cuando más hacen falta para
    entender qué pasó (R9.2, #292).
    """
    if not invocacion.result.success:
        return ExecuteResponse(
            tool=name,
            server=invocacion.server,
            status=ExecuteStatus.ERROR,
            arguments=arguments,
            detail=invocacion.result.error,
        )

    return ExecuteResponse(
        tool=name,
        server=invocacion.server,
        status=ExecuteStatus.OK,
        arguments=arguments,
        data=invocacion.result.data,
    )
