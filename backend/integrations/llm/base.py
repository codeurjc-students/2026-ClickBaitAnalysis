"""El contrato común de los backends del modelo de lenguaje: `LLMBackend`.

El agente (#188) habla con el modelo a través de esta interfaz, sin saber qué
servidor hay detrás: R13.6 pide que sea intercambiable por configuración. Hoy
hay una implementación, `ollama.py`, y la elige `factory.py`.

Los tipos son NEUTRALES, no el formato de Ollama: con otro proveedor, el agente
no cambiaría. Las claves van en inglés, como las del dominio (#134), porque
van al contrato de la API: `Medidas` en cada paso de `GET /chat/{id}` y
`Disponibilidad` en `GET /agent` (#189).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from backend.core.models import ToolResult


class LlamadaHerramienta(TypedDict):
    """Una herramienta que el modelo pide ejecutar, con sus argumentos."""

    name: str
    arguments: dict


class Mensaje(TypedDict):
    """Un turno de la conversación con el modelo.

    `tool_calls` sólo aparece en los del asistente que piden herramientas, y
    `tool_name` sólo en los de rol `tool`, que le devuelven un resultado.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: NotRequired[list[LlamadaHerramienta]]
    tool_name: NotRequired[str]


class Herramienta(TypedDict):
    """Lo que el modelo necesita saber de una herramienta para poder pedirla.

    `parameters` es el `inputSchema` que publica MCP, que ya es JSON Schema: pasa
    tal cual.
    """

    name: str
    description: str
    parameters: dict


class Medidas(TypedDict):
    """Lo que el propio servidor dice que costó una respuesta.

    `prompt_tokens` es lo que el servidor EVALUÓ del prompt en esta llamada. Con
    la ventana llena recorta en silencio, y esto es lo único que lo delata
    (spike rehecho en la A40, PR #176). Es `None` si el servidor no lo informa.
    Si reutiliza lo ya evaluado en una vuelta anterior, podría contar menos que
    la conversación entera: medirlo es de #188, antes de usarlo como tamaño.
    """

    prompt_tokens: int | None
    output_tokens: int | None
    load_s: float
    total_s: float


class Respuesta(TypedDict):
    """Una vuelta del modelo: su texto, las herramientas que pide, o las dos."""

    content: str
    tool_calls: list[LlamadaHerramienta]
    metrics: Medidas


Estado = Literal["not_configured", "unreachable", "model_missing", "available"]


@dataclass(frozen=True)
class Disponibilidad:
    """Si el asistente se puede usar ahora, y por qué no, si no se puede.

    `detail` es PÚBLICO: la interfaz lo enseña para explicar por qué no hay
    asistente (R6.14). Por eso se redacta aquí, nunca con el texto de una
    excepción (#163).
    """

    status: Estado
    detail: str
    model: str | None = None


class LLMBackend(ABC):
    """Un servidor de modelos de lenguaje con el que se puede conversar."""

    @abstractmethod
    async def chat(
        self,
        messages: list[Mensaje],
        tools: list[Herramienta],
        *,
        think: bool = False,
    ) -> ToolResult:
        """Una vuelta: el modelo lee la conversación y responde, pide
        herramientas, o las dos cosas.

        DEBE devolver `ToolResult.ok(Respuesta)`, o un fallo con un mensaje que
        se pueda publicar tal cual: un fallo que viaja como valor lo sanea
        quien lo crea (#185).
        """

    @abstractmethod
    async def disponibilidad(self) -> Disponibilidad:
        """Si el servidor responde y tiene el modelo configurado, preguntado
        ahora mismo. Nunca lanza: todo fallo es un estado."""
