"""Lo que produce el agente: la traza, paso a paso, y el resultado (#188, R13.3).

Viven aparte del bucle porque la API los publicará (#189) y tiene que poder
importarlos sin él. Por lo mismo, las claves van en inglés, como las del dominio
(#134) y las de `integrations/llm/base.py`.

**La traza es lo que lee la interfaz, no la narración.** Cada herramienta lleva
su resultado estructurado COMPLETO, y de ahí salen las tarjetas (R6.12): así el
veredicto nunca pasa por el texto del modelo (R13.4). Las vueltas del modelo van
también, con sus medidas, porque sin ellas no se sabe cuánto ocupó cada una de
la ventana.

`data` y `metrics` son libres para quien los consuma: el `data` de cada
herramienta tiene la forma que declare ella, igual que el de cada señal.
"""

from typing import Any, Literal, TypedDict

from backend.integrations.llm.base import Medidas


class Turno(TypedDict):
    """Un turno anterior de la conversación, sólo con su texto.

    Sin los resultados de las herramientas: la ventana es de 8.192 tokens y el
    catálogo ya ocupa 2.629 (decidido al definir H5). El servidor no guarda nada
    entre turnos; el historial lo manda el cliente.
    """

    role: Literal["user", "assistant"]
    content: str


class PasoModelo(TypedDict):
    """Una vuelta del modelo: lo que escribió, qué pidió y lo que costó."""

    kind: Literal["model"]
    round: int
    content: str
    tool_calls: list[str]
    metrics: Medidas


class PasoHerramienta(TypedDict):
    """Una herramienta que pidió el modelo, con su resultado o su error.

    `data` es el resultado estructurado ENTERO, aunque al modelo le llegue
    recortado. `error` es público: se enseña tal cual (#163, #89). `server` es
    `None` si no se llegó a ejecutar en ningún servidor.
    """

    kind: Literal["tool"]
    round: int
    name: str
    arguments: dict
    status: Literal["ok", "error"]
    data: Any | None
    error: str | None
    server: str | None
    duration_s: float


Paso = PasoModelo | PasoHerramienta

EstadoFinal = Literal["answered", "empty_answer", "max_rounds", "failed"]


class Resultado(TypedDict):
    """Cómo acabó una consulta.

    - `answered`: el modelo respondió con texto.
    - `empty_answer`: respondió sin texto. Es el modo de fallo del spike #82, y
      las tarjetas se enseñan igual (R6.13).
    - `max_rounds`: se agotaron las vueltas pidiendo herramientas.
    - `failed`: no se pudo llegar al modelo o no había herramientas; `detail`
      dice por qué, en una frase que se puede publicar.
    """

    status: EstadoFinal
    answer: str
    detail: str | None
    steps: list[Paso]
    rounds: int
    total_s: float
