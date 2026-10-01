"""Cómo se describe un error en una salida pública.

**Dos funciones, porque hay dos destinatarios.** `describir_error` escribe para
quien INSPECCIONA el sistema —el detalle de `/health` y del catálogo, que la
interfaz marca como técnico— y da el código HTTP o el nombre del tipo.
`mensaje_publico` escribe para quien LEE UN RESULTADO —la tarjeta de una señal
caída (#89)— y no dice ni nombres de clase ni nada de cómo está hecho el
sistema por dentro: un `KeyError: 'is_clickbait'` le cuenta a un tercero cómo
está estructurado el código.

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


# Predicados SIN SUJETO, a propósito: quien llama pone el suyo —«La señal…», «El
# modelo `X`…», «La llamada a la API externa…»— y la frase se lee entera. Con el
# sujeto dentro habría que elegir uno, y ninguno vale para los tres sitios.
_TARDO = "tardó demasiado en responder"
_SIN_CONEXION = "no pudo contactar con el servicio externo"
_NO_PREVISTO = (
    "falló por un motivo no previsto; el detalle técnico queda en el log del servidor"
)


def mensaje_publico(excepcion: BaseException) -> str:
    """Qué le pasó, para quien lee un resultado y no va a depurar nada.

    Devuelve un predicado sin sujeto, y **nunca** nombres de clase, mensajes de
    librerías ni trazas: eso se registra en el log, que es donde sirve.

    Las familias son las que cambian lo que puede hacer quien lo lee: si la cosa
    tardó, si no se pudo llegar al servicio, o si respondió mal. Todo lo demás es
    «no previsto», y ahí la única acción posible es mirar el log.
    """
    if isinstance(excepcion, BaseExceptionGroup):
        motivos = dict.fromkeys(mensaje_publico(hija) for hija in excepcion.exceptions)
        return ", ".join(motivos)
    # El orden importa: `httpx.TimeoutException` hereda de `TransportError`, así
    # que comprobar la conexión antes se tragaría los timeouts.
    if isinstance(excepcion, TimeoutError | httpx.TimeoutException):
        return _TARDO
    if isinstance(excepcion, httpx.HTTPStatusError):
        return f"recibió un {describir_error(excepcion)} del servicio externo"
    if isinstance(excepcion, httpx.TransportError):
        return _SIN_CONEXION
    return _NO_PREVISTO
