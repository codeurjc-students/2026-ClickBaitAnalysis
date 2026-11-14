"""`log_tool_invocation`: el decorador que registra cada invocación de una tool.

Una línea `tool.invoke` por llamada, con los argumentos, la duración y el
resultado; si falla, `tool.invoke.failed` con la traza completa, y **relanza**.
El decorador observa, no decide qué se responde: antes devolvía el error como
texto, y MCP lo daba por un resultado válido, con `isError` a false (#100).

**Lo que relanza, desde #292 (R12.7).** Un `ToolError` sale tal cual: lo lanza
la herramienta a propósito, con una frase ya pensada para publicarse (#89).
Cualquier otra excepción es un fallo que nadie redactó —un `KeyError` de una
respuesta con otra forma, el error de validación de Pydantic de un titular en
blanco— y FastMCP la publicaría entera como «Error executing tool …: <texto>»:
por `/tools/{name}/execute` y hacia el modelo del agente, contra la regla de
`core/errores.py` (#163). Sale como `ToolError` con la frase de
`mensaje_publico`, y el texto se queda en la traza del registro.
"""

import functools
import time
import traceback

import structlog
from mcp.server.fastmcp.exceptions import ToolError

from backend.core.errores import mensaje_publico

log = structlog.get_logger()


def log_tool_invocation(func):
    @functools.wraps(
        func
    )  # Preserva el nombre y docstring de la función original. functools.wraps es un decorador que se utiliza para preservar la información de la función original.
    async def wrapper(
        **kwargs,
    ):  # * y **=> acepta cualquier número de argumentos posicionales y de palabras clave.
        #
        start = time.perf_counter()  # perf_counte = time.time() avanzado.
        try:
            result = await func(**kwargs)
            duration_ms = round(
                (time.perf_counter() - start) * 1000, 2
            )  # 2 decimales, ms
            log.info(
                "tool.invoke",
                tool=func.__name__,
                params={
                    "kwargs": kwargs,
                },
                # todo es kwargs ya que pasamos los parámetros como JSON objects
                duration_ms=duration_ms,
                success=True,
            )  # recuerda, key-value del logger.
            # __name__ => nombre de la función original, sin el decorador. __ se utiliza para acceder a atributos especiales de los objetos en Python.
            return result
        except Exception as error:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log.error(
                "tool.invoke.failed",
                tool=func.__name__,
                params={
                    "kwargs": kwargs,
                },
                duration_ms=duration_ms,
                success=False,
                exception=traceback.format_exc(),  # Guarda el traceback completo como string
            )
            # RELANZAR, no devolver un texto. Devolviéndolo, la excepción no
            # llegaba nunca a MCP: el protocolo la veía como un resultado válido
            # (`isError` a False) y el consumidor no podía distinguir un fallo de
            # un análisis correcto. Además, con salida estructurada declarada,
            # esa cadena tampoco encaja en el esquema y el motivo real se perdía
            # detrás de un error de validación de Pydantic.
            #
            # El decorador es para OBSERVAR, no para decidir qué se responde: el
            # traceback completo queda en el log, y quien llama recibe el error.
            if isinstance(error, ToolError):
                raise
            # Lo que no es un `ToolError` sale con una frase pública (#292): su
            # texto ya está en el `exception` de arriba, y el `from` conserva la
            # causa para quien depure.
            raise ToolError(f"La herramienta {mensaje_publico(error)}.") from error

    return wrapper
