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
            return "Internal error while executing tool"

    return wrapper
