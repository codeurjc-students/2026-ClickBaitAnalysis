"""Ejecución de una herramienta concreta — ``POST /tools/{name}/execute``.

Sus dos consumidores son ejecutar **una señal suelta** —sólo el sentimiento, sin
lanzar las cuatro— y **traer una noticia** desde la pantalla de análisis. No un
catálogo que haga de lanzador.

**Los parámetros se validan antes de invocar** (R4.5), contra el ``inputSchema``
que el propio servidor publica. Se podría dejar que validara MCP, pero entonces
un argumento mal escrito llegaría como fallo de ejecución y sería
indistinguible de un análisis que salió mal: validando aquí, la API puede
responder 422 y decir qué campo falla.

**Tres errores, tres categorías distintas:**

- La herramienta no existe → **404**. La petición pide algo que no hay.
- Los argumentos no encajan en su esquema → **422**. La petición está mal
  formada.
- La herramienta se ejecuta y falla → **200 con ``status`` en ``error``**. La
  petición era correcta y el servidor la atendió; lo que falló es el análisis.
  Mismo criterio que en ``/analyze``, donde una señal caída no tumba la
  respuesta.
"""

import structlog
from jsonschema import Draft7Validator
from mcp.types import CallToolResult, Tool

from backend.api.mcp_session import open_session
from backend.api.schemas import ExecuteResponse, ExecuteStatus
from backend.config.settings import settings

log = structlog.get_logger()


class ToolNotFound(Exception):
    """La herramienta no está en ningún servidor configurado."""


class InvalidArguments(Exception):
    """Los argumentos no encajan en el esquema que publica la herramienta."""


async def execute_tool(name: str, arguments: dict) -> ExecuteResponse:
    """Localiza la herramienta, valida los argumentos y la invoca.

    **Nada se lanza desde dentro de la sesión.** La sesión MCP abre un *task
    group* de anyio, y anyio envuelve en un ``ExceptionGroup`` lo que se lance
    ahí dentro: el ``except InvalidArguments`` de la ruta no lo capturaría y
    saldría un 500 donde toca un 422. Por eso ``_intentar`` **devuelve** lo que
    ha pasado y es aquí, ya fuera, donde se decide qué excepción sale.
    """
    for url in settings.mcp_servers:
        intento = await _intentar(url, name, arguments)
        if intento is None:
            continue  # esta herramienta no está en este servidor

        problemas, resultado, servidor = intento
        if problemas:
            raise InvalidArguments(problemas)
        return _envolver(resultado, name, servidor)

    raise ToolNotFound(name)


async def _intentar(
    url: str, name: str, arguments: dict
) -> tuple[str | None, CallToolResult | None, str] | None:
    """Busca la herramienta en un servidor y, si está, la valida y la invoca.

    Devuelve ``None`` si no la tiene. Si la tiene, ``(problemas, resultado,
    servidor)``: con ``problemas`` los argumentos no pasaron la validación y no
    se llegó a invocar nada.
    """
    async with open_session(url, settings.mcp_execute_timeout) as (
        session,
        inicializacion,
    ):
        tools = {t.name: t for t in (await session.list_tools()).tools}
        if name not in tools:
            return None

        servidor = inicializacion.serverInfo.name
        problemas = _problemas(arguments, tools[name])
        if problemas:
            return problemas, None, servidor

        return None, await session.call_tool(name, arguments), servidor


def _problemas(arguments: dict, tool: Tool) -> str | None:
    """Valida los argumentos contra el ``inputSchema``; None si están bien.

    Se acumulan **todos** los problemas en vez de parar en el primero: quien
    rellena un formulario prefiere corregirlo de una vez a descubrirlos de uno
    en uno.
    """
    errores = sorted(
        Draft7Validator(tool.inputSchema).iter_errors(arguments),
        key=lambda e: list(e.path),
    )
    if not errores:
        return None

    return "; ".join(
        f"{'.'.join(str(p) for p in e.path) or '(raíz)'}: {e.message}" for e in errores
    )


def _envolver(resultado: CallToolResult, name: str, servidor: str) -> ExecuteResponse:
    """Traduce la respuesta del protocolo al contrato de la API.

    ``isError`` es fiable desde que las herramientas **lanzan** en vez de
    devolver el mensaje de error: antes un fallo llegaba por el mismo canal que
    un resultado válido y aquí no habría forma de distinguirlos.
    """
    if resultado.isError:
        motivo = resultado.content[0].text if resultado.content else "Error desconocido"
        log.warning("tool.execute.failed", tool=name, motivo=motivo)
        return ExecuteResponse(
            tool=name,
            server=servidor,
            status=ExecuteStatus.ERROR,
            detail=motivo,
        )

    return ExecuteResponse(
        tool=name,
        server=servidor,
        status=ExecuteStatus.OK,
        data=resultado.structuredContent,
    )
