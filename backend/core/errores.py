"""Cómo se describe un error en una salida pública.

**La regla (#163): el texto de una excepción de librería no sale hacia fuera.**
Un 401 de httpx lleva la URL entera en su mensaje, y Guardian y NYT llevan la
clave en ella: `health.py` la publicó así por `GET /health`. Salida pública es
cualquier respuesta HTTP, cualquier cosa que pinte el frontend y cualquier
resultado de una tool MCP, que recibiría el LLM del agente.

Vive aquí y no en cada consumidor porque la usan dos capas —`core/health.py` y
`api/catalog.py`, y mañana el agente—, y escrita dos veces acabaría divergiendo.

Qué ve el catálogo cuando un servidor MCP no responde, medido el 2026-09-17
(#164), y por qué hacía falta abrir los grupos:

- nombre del servicio rechazado → grupo con `httpx.HTTPStatusError` (421)
- puerto cerrado o nombre inexistente → grupo con `httpx.ConnectError`
- ruta que no existe → grupo DENTRO de otro grupo, con `McpError`
- servidor que acepta y no contesta → `TimeoutError`, sin grupo

El cliente MCP lee y escribe a la vez, en tareas concurrentes, y los errores de
esas tareas llegan envueltos en `ExceptionGroup` — cuyo texto, «unhandled errors
in a TaskGroup (1 sub-exception)», era lo único que enseñaba la pantalla.
"""

import httpx


def describir_error(excepcion: BaseException) -> str:
    """El motivo de un error, en una forma que se puede publicar.

    Un error HTTP da su código y su nombre (`HTTP 421 Misdirected Request`);
    cualquier otro, el nombre de su tipo (`ConnectError`). Un grupo se abre
    —a cualquier profundidad— y se juntan los motivos distintos, en orden.
    """
    if isinstance(excepcion, BaseExceptionGroup):
        # `dict.fromkeys` y no `set`: quita repetidos conservando el orden.
        motivos = dict.fromkeys(describir_error(hija) for hija in excepcion.exceptions)
        return ", ".join(motivos)
    if isinstance(excepcion, httpx.HTTPStatusError):
        respuesta = excepcion.response
        return f"HTTP {respuesta.status_code} {respuesta.reason_phrase}"
    return type(excepcion).__name__
