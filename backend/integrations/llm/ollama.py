"""Backend del modelo de lenguaje: el servidor Ollama de la GPU (`OllamaClient`).

Implementa `LLMBackend` contra la API de chat de Ollama. En despliegue se llega
por el túnel inverso de #181, en `host.docker.internal:11434` desde el
contenedor de la API, y Ollama sólo está arrancado mientras alguien tiene
abierta una sesión con `gpu-sesion`: «apagado» es su estado normal, no una
avería.

Dos caminos, a propósito:

- **El chat pasa por `BaseAPI.make_request`**, como `nlp/remote.py`: hereda los
  mensajes públicos de #89 y el log `api.call`. Y NO reintenta: una llamada al
  modelo cuesta segundos de GPU, y repetirla tras un timeout la duplicaría.
- **La disponibilidad no**, porque `make_request` convierte cualquier fallo en
  una frase, y aquí hace falta saber QUÉ pasó: una conexión rechazada significa
  que nadie escucha, que la sesión está cerrada. Va con `httpx` directamente.

No lee `settings`: recibe su configuración, como los detectores NLP (#119). Y
`num_ctx` va SIEMPRE explícito: Ollama 0.34.2 elige el suyo según la VRAM
(32.768 en la A40, #181), y con uno pequeño recorta el catálogo de
herramientas sin avisar (spike rehecho en la A40, PR #176).
"""

import json

import httpx
import structlog

from backend.core.base_api import BaseAPI
from backend.core.errores import mensaje_publico
from backend.core.models import ToolResult
from backend.integrations.llm.base import (
    Disponibilidad,
    Herramienta,
    LlamadaHerramienta,
    LLMBackend,
    Mensaje,
    Respuesta,
)

log = structlog.get_logger()

# La disponibilidad se pregunta cada vez que hace falta: una conexión rechazada
# se sabe en 0,1 ms (#181). Si en dos segundos no contesta, para quien espera es
# lo mismo que apagado.
CORTE_DISPONIBILIDAD = 2.0


class OllamaClient(BaseAPI, LLMBackend):
    MAX_RETRIES = 0

    def __init__(
        self,
        url: str,
        model: str,
        *,
        num_ctx: int,
        keep_alive: str,
        timeout: float,
    ) -> None:
        super().__init__()
        # `make_request` compone `BASE_URL + endpoint`: sin la barra final, la
        # ruta quedaría pegada al puerto.
        self.BASE_URL = url.rstrip("/") + "/"
        self.TIMEOUT = timeout
        self.model = model
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive

    async def chat(
        self,
        messages: list[Mensaje],
        tools: list[Herramienta],
        *,
        think: bool = False,
    ) -> ToolResult:
        cuerpo: dict = {
            "model": self.model,
            "messages": [_mensaje_a_ollama(mensaje) for mensaje in messages],
            "stream": False,
            "think": think,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": self.num_ctx},
        }
        if tools:
            cuerpo["tools"] = [
                _herramienta_a_ollama(herramienta) for herramienta in tools
            ]

        resultado = await self.make_request("api/chat", "POST", json=cuerpo)
        if not resultado.success:
            return resultado

        try:
            return ToolResult.ok(_leer_respuesta(resultado.unwrap()))
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            # La respuesta cruda va al log y NO a la salida pública: un fallo
            # que viaja como valor se publica tal cual, así que lo sanea quien
            # lo crea (#185).
            log.warning(
                "llm.respuesta_inesperada",
                modelo=self.model,
                tipo=type(error).__name__,
                detalle=str(error),
                respuesta=str(resultado.data)[:1000],
            )
            return ToolResult.fail(
                f"El modelo `{self.model}` {mensaje_publico(error)}."
            )

    async def disponibilidad(self) -> Disponibilidad:
        try:
            async with httpx.AsyncClient(timeout=CORTE_DISPONIBILIDAD) as cliente:
                version = await cliente.get(f"{self.BASE_URL}api/version")
                version.raise_for_status()
                etiquetas = await cliente.get(f"{self.BASE_URL}api/tags")
                etiquetas.raise_for_status()
                nombres = {modelo["name"] for modelo in etiquetas.json()["models"]}
        except httpx.ConnectError as error:
            if _rechazada(error):
                return Disponibilidad(
                    "unreachable",
                    "El asistente está apagado: el servidor del modelo se arranca "
                    "bajo demanda y ahora no está en marcha.",
                    self.model,
                )
            return self._no_disponible(error)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            return self._no_disponible(error)

        if _con_etiqueta(self.model) not in {
            _con_etiqueta(nombre) for nombre in nombres
        }:
            return Disponibilidad(
                "model_missing",
                f"El servidor del modelo está en marcha, pero no tiene `{self.model}`.",
                self.model,
            )
        return Disponibilidad("available", "El asistente está disponible.", self.model)

    def _no_disponible(self, error: Exception) -> Disponibilidad:
        log.warning(
            "llm.disponibilidad.fallo",
            url=self.BASE_URL,
            tipo=type(error).__name__,
            detalle=str(error),
        )
        return Disponibilidad(
            "unreachable",
            f"La consulta al servidor del modelo {mensaje_publico(error)}.",
            self.model,
        )


def _rechazada(error: BaseException) -> bool:
    """Si en la cadena de causas hay una conexión rechazada.

    Es lo único que significa «nadie escucha»: la máquina contesta, pero no hay
    ningún Ollama detrás (#181). Un nombre que no resuelve también da
    `ConnectError`, y decir entonces «está apagado» sería mentir: es un fallo
    de configuración. Por eso sólo este caso recibe la frase de la sesión.
    """
    actual: BaseException | None = error
    while actual is not None:
        if isinstance(actual, ConnectionRefusedError):
            return True
        actual = actual.__cause__ or actual.__context__
    return False


def _con_etiqueta(nombre: str) -> str:
    """`qwen3.5` y `qwen3.5:latest` son el mismo modelo para Ollama."""
    return nombre if ":" in nombre else f"{nombre}:latest"


def _mensaje_a_ollama(mensaje: Mensaje) -> dict:
    salida: dict = {"role": mensaje["role"], "content": mensaje["content"]}
    if "tool_calls" in mensaje:
        salida["tool_calls"] = [
            {"function": {"name": llamada["name"], "arguments": llamada["arguments"]}}
            for llamada in mensaje["tool_calls"]
        ]
    if "tool_name" in mensaje:
        salida["tool_name"] = mensaje["tool_name"]
    return salida


def _herramienta_a_ollama(herramienta: Herramienta) -> dict:
    return {
        "type": "function",
        "function": {
            "name": herramienta["name"],
            "description": herramienta["description"],
            "parameters": herramienta["parameters"],
        },
    }


def _leer_respuesta(datos: dict) -> Respuesta:
    mensaje = datos["message"]
    llamadas: list[LlamadaHerramienta] = []
    for llamada in mensaje.get("tool_calls") or []:
        funcion = llamada["function"]
        argumentos = funcion.get("arguments") or {}
        # Ollama los manda como objeto; otros servidores, como texto JSON.
        if isinstance(argumentos, str):
            argumentos = json.loads(argumentos)
        if not isinstance(argumentos, dict):
            raise TypeError(f"argumentos de «{funcion['name']}» sin forma de objeto")
        llamadas.append({"name": funcion["name"], "arguments": argumentos})

    return {
        "content": mensaje.get("content") or "",
        "tool_calls": llamadas,
        "metrics": {
            # `None` si no viene, y no 0: un cero inventado se leería como «no
            # leyó nada».
            "prompt_tokens": datos.get("prompt_eval_count"),
            "output_tokens": datos.get("eval_count"),
            "load_s": datos.get("load_duration", 0) / 1e9,
            "total_s": datos.get("total_duration", 0) / 1e9,
        },
    }
