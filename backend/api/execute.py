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
- El servidor tarda más de la cuenta → **504**. Ver ``ToolTimeout``.
"""

import asyncio

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


class ToolTimeout(Exception):
    """El servidor MCP no respondió dentro de ``mcp_execute_timeout``.

    Es su **propia** categoría y no un ``ExecuteResponse`` con ``status`` en
    ``error``, porque no son lo mismo: aquel significa «la herramienta se ejecutó
    y falló», y aquí puede haber salido perfectamente.

    Lo que ha fallado es la espera, no el análisis. Decirle a quien mira que «el
    análisis falló» sería mentirle; un 504 le dice que está tardando demasiado,
    que es lo que pasa de verdad.
    """


async def execute_tool(name: str, arguments: dict) -> ExecuteResponse:
    """Localiza la herramienta, valida los argumentos y la invoca.

    **Nada se lanza desde dentro de la sesión.** La sesión MCP abre un *task
    group* de anyio, y anyio envuelve en un ``ExceptionGroup`` lo que se lance
    ahí dentro: el ``except InvalidArguments`` de la ruta no lo capturaría y
    saldría un 500 donde toca un 422. Por eso ``_intentar`` **devuelve** lo que
    ha pasado y es aquí, ya fuera, donde se decide qué excepción sale.
    """
    for url in settings.mcp_servers:
        try:
            intento = await _intentar(url, name, arguments)

        # `except*` y no `except`: lo que sale de la sesión viene envuelto DOS
        # veces —un task group de anyio por capa, `streamable_http_client` y
        # `ClientSession`— y un `except TimeoutError` no casa con un grupo:
        #
        #     ExceptionGroup: 'unhandled errors in a TaskGroup'
        #       ExceptionGroup: 'unhandled errors in a TaskGroup'
        #         TimeoutError          <- lo que de verdad pasó
        #
        # Ese envoltorio no se puede desactivar: es la semántica de los task
        # groups, donde pueden fallar VARIAS tareas a la vez y no existe «la»
        # excepción que devolver.
        #
        # `except*` (Python 3.11+) desmonta el grupo y compara por tipo a
        # CUALQUIER profundidad, así que cubre también el caso sin envolver y no
        # depende de cuántas capas ponga la librería el día de mañana.
        #
        # Diferencia con un `except` normal, comprobada: `except*` puede entrar
        # en VARIAS ramas, porque un grupo admite fallos de tipos distintos. Si
        # llegara un timeout JUNTO A otro fallo, saldría un grupo con el
        # `ToolTimeout` dentro y la ruta respondería 500 en lugar de 504. Se
        # asume: un timeout más un fallo independiente no es realmente «no
        # respondió a tiempo».
        #
        # Si esa robustez llegara a hacer falta, la alternativa —descartada por
        # ser maquinaria a mano donde el lenguaje ya trae herramienta— era
        # recorrer el árbol y quedarse con el 504 siempre:
        #
        #     def _hay_timeout(exc: BaseException) -> bool:
        #         if isinstance(exc, BaseExceptionGroup):
        #             return any(_hay_timeout(hija) for hija in exc.exceptions)
        #         return isinstance(exc, TimeoutError)
        #
        #     except BaseExceptionGroup as grupo:
        #         if not _hay_timeout(grupo):
        #             raise
        #         raise ToolTimeout(name) from grupo
        except* TimeoutError:
            log.warning("tool.execute.timeout", tool=name, url=url)
            raise ToolTimeout(name) from None

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

    El ``asyncio.timeout`` acota **la operación entera** —handshake, catálogo y
    llamada— y no sólo ``call_tool``, para que un servidor lento en presentarse
    tampoco deje la petición sin techo.

    Es el que de verdad corta. El ``timeout`` de httpx que se le pasa a
    ``open_session`` mide **inactividad entre bytes**, no duración: con una tool
    que tarda más de la cuenta no salta, y la petición se queda colgada para
    siempre en vez de fallar (#113, reproducido — 25 s de espera con un corte
    pedido de 2). Se conserva igualmente porque sí cubre lo suyo: un servidor que
    acepta la conexión y deja de enviar.
    """
    async with (
        asyncio.timeout(settings.mcp_execute_timeout),
        open_session(url, settings.mcp_execute_timeout) as (
            session,
            inicializacion,
        ),
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
