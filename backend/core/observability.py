# Decorador que registra cada invocación de una tool

import functools
import time
import traceback

import structlog

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
        except Exception:
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
            raise

    return wrapper
