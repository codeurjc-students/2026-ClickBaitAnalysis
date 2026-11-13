"""Backend del modelo de lenguaje que reproduce respuestas grabadas (#265).

Para la defensa, cuando no se puede servir el modelo: la máquina 2 es
compartida, y el día de la demostración puede estar ocupada o caída. Este
backend reproduce lo que escribió el 27B al grabar la conversación del paso 6
de `docs/demostracion.md`, y las herramientas se ejecutan de verdad: el agente
no sabe que habla con una grabación. La graba `spikes/grabar_demostracion.py`,
y el fichero vive en `grabaciones/`, dentro de la imagen.

Lo que no se deduce leyéndolo:

- **Sólo narra lo que se ve en las tarjetas** (R13.4). Antes de cada vuelta
  comprueba que lo que recibe el modelo —el prompt de sistema y el resultado de
  cada herramienta de este turno— es lo que recibió al grabar. Si algo difiere,
  no reproduce lo grabado: devuelve una frase fija que lo dice. Las cifras, con
  un margen de una unidad en la tercera cifra decimal (`MARGEN`): el agente las
  redondea a tres decimales antes de dárselas al modelo, y grabar en un equipo
  y reproducir en otro puede mover ese redondeo. Lo demás, exacto: un veredicto
  o una etiqueta que cambian no pasan.
- **La consulta se busca por el ÚLTIMO turno del usuario**, no por la
  conversación entera: la pantalla recorta el historial quitando los turnos más
  antiguos (`historialQueCabe`), y empezar una conversación nueva a mitad
  dejaría sin reproducir los turnos 2 y 3. Lo que se narra se comprueba igual.
- **La vuelta se cuenta por las respuestas del modelo desde ese turno**: las
  que piden herramientas y la vacía o cortada a la que sigue `PEDIR_RESPUESTA`
  (#208). Así se reproduce también una vuelta cortada, si se grabó.
- **No lee `settings`** (#119): la factoría le pasa la ruta. Lee el fichero en
  el primer uso, y si no está o no se puede leer, lo dice como un estado y no
  lanza: la pantalla tiene que poder explicar por qué no hay asistente (R6.14).
- **Las medidas son las de la grabación**: lo que costó de verdad el día que se
  grabó. Las frases fijas no tienen medidas: no las escribió ningún modelo.
"""

import copy
import json
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, TypedDict, TypeGuard

import structlog
from pydantic import TypeAdapter, ValidationError

from backend.core.models import ToolResult
from backend.integrations.llm.base import (
    Disponibilidad,
    Herramienta,
    LLMBackend,
    Mensaje,
    Respuesta,
)
from backend.integrations.llm.model_card import FichaLLM

log = structlog.get_logger()

# Donde viven las grabaciones, dentro del paquete para que `COPY backend/` las
# lleve a la imagen. La factoría elige el fichero por su nombre, como los
# prompts (`llm_grabacion`).
CARPETA = Path(__file__).resolve().parent / "grabaciones"

# Una unidad en la tercera cifra decimal, que es con lo que lee el modelo las
# cifras (`decimales_para_el_modelo`). La holgura es por la representación en
# coma flotante: 0,951 − 0,950 da 0,0010000000000000009, y se quedaría fuera.
MARGEN = 0.001
_HOLGURA = 1e-9

NO_GRABADA = (
    "Esta consulta no está entre las grabadas, así que no hay respuesta que "
    "reproducir: el modelo no está en marcha ahora. Las grabadas son: {consultas}."
)
HA_CAMBIADO = (
    "Lo que recibe el modelo ha cambiado desde la grabación del {fecha}: las "
    "instrucciones o el resultado de alguna herramienta no son los de entonces. "
    "No se reproduce lo grabado, porque contaría algo distinto de lo que se ve "
    "en las tarjetas. Las tarjetas son de ahora: las calcularon las herramientas."
)
SIN_GRABACION = (
    "No se encuentra la grabación de respuestas del asistente, o no se puede leer."
)


class ResultadoGrabado(TypedDict):
    """El resultado de una herramienta, tal como lo leyó el modelo al grabar:
    el texto JSON del mensaje de rol `tool`, con las cifras ya redondeadas."""

    tool_name: str
    content: str


class VueltaGrabada(TypedDict):
    """Una vuelta del modelo y lo que recibió antes de darla.

    `tool_results` son los resultados que llegaron DESDE LA VUELTA ANTERIOR: en
    la primera, ninguno. Los de una vuelta son, entonces, los de todas las
    anteriores del turno seguidos.
    """

    tool_results: list[ResultadoGrabado]
    response: Respuesta


class TurnoGrabado(TypedDict):
    """Una consulta del usuario y las vueltas con que la contestó el modelo."""

    query: str
    rounds: list[VueltaGrabada]


class PromptGrabado(TypedDict):
    """El prompt de sistema con el que se grabó, entero: se compara letra a letra."""

    name: str
    text: str


class Tomas(TypedDict):
    """Cuántas tomas de la conversación se grabaron y cuál se reproduce (#265)."""

    recorded: int
    chosen: int


class Grabacion(TypedDict):
    """El fichero de una grabación.

    `conditions` es libre: la versión de Ollama, la ventana, el muestreo, dónde
    corrían las señales… Lo escribe el guion que graba, y aquí no se lee.
    """

    model: str
    model_digest: str
    recorded_at: date
    commit: str
    prompt: PromptGrabado
    takes: Tomas
    conditions: dict[str, Any]
    turns: list[TurnoGrabado]


class InfoGrabacion(TypedDict):
    """Lo que la pantalla necesita para decir que las respuestas son grabadas.

    Va al contrato de `GET /agent`, así que las claves van en inglés.
    """

    model: str
    recorded_at: date
    commit: str


_LECTOR = TypeAdapter(Grabacion)

_COMILLAS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def normalizar(consulta: str) -> str:
    """La consulta como se busca: sin distinguir mayúsculas, espacios ni
    comillas tipográficas, que aparecen al pegar desde un procesador de textos.
    En forma NFC, para que una tilde escrita como dos caracteres sea la misma."""
    compuesta = unicodedata.normalize("NFC", consulta).translate(_COMILLAS)
    return " ".join(compuesta.split()).casefold()


class ReproductorGrabado(LLMBackend):
    """Un `LLMBackend` que contesta con lo que contestó el modelo al grabar."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self._leida = False
        self._grabacion: Grabacion | None = None
        self._turnos: dict[str, TurnoGrabado] = {}

    def _cargar(self) -> Grabacion | None:
        """La grabación, leída la primera vez. `None` si no se pudo leer."""
        if not self._leida:
            self._leida = True
            try:
                self._grabacion = _LECTOR.validate_json(self.ruta.read_bytes())
            except (OSError, ValidationError) as error:
                log.warning(
                    "grabado.ilegible",
                    ruta=str(self.ruta),
                    tipo=type(error).__name__,
                    detalle=str(error)[:1000],
                )
            else:
                self._turnos = {
                    normalizar(turno["query"]): turno
                    for turno in self._grabacion["turns"]
                }
        return self._grabacion

    async def chat(
        self,
        messages: list[Mensaje],
        tools: list[Herramienta],
        *,
        think: bool = False,
    ) -> ToolResult:
        grabacion = self._cargar()
        if grabacion is None:
            return ToolResult.fail(SIN_GRABACION)

        posicion = _ultima_consulta(messages)
        turno = (
            None
            if posicion is None
            else self._turnos.get(normalizar(messages[posicion]["content"]))
        )
        if posicion is None or turno is None:
            log.info("grabado.no_grabada")
            consultas = "; ".join(
                f"«{grabado['query']}»" for grabado in grabacion["turns"]
            )
            return ToolResult.ok(_frase(NO_GRABADA.format(consultas=consultas)))

        posteriores = messages[posicion + 1 :]
        vuelta = sum(mensaje["role"] == "assistant" for mensaje in posteriores)
        ha_cambiado = HA_CAMBIADO.format(fecha=_fecha(grabacion["recorded_at"]))
        if vuelta >= len(turno["rounds"]):
            log.warning("grabado.vuelta_de_mas", vuelta=vuelta + 1)
            return ToolResult.ok(_frase(ha_cambiado))

        if messages[0]["content"] != grabacion["prompt"]["text"]:
            log.warning("grabado.ha_cambiado", vuelta=vuelta + 1, motivo="prompt")
            return ToolResult.ok(_frase(ha_cambiado))

        recibidos = [
            (mensaje.get("tool_name"), mensaje["content"])
            for mensaje in posteriores
            if mensaje["role"] == "tool"
        ]
        grabados = [
            (resultado["tool_name"], resultado["content"])
            for anterior in turno["rounds"][: vuelta + 1]
            for resultado in anterior["tool_results"]
        ]
        if not _coinciden(recibidos, grabados):
            log.warning("grabado.ha_cambiado", vuelta=vuelta + 1, motivo="resultados")
            return ToolResult.ok(_frase(ha_cambiado))

        # Una copia: el agente guarda las llamadas en la conversación, y la
        # grabación tiene que quedar intacta para la siguiente vez.
        return ToolResult.ok(copy.deepcopy(turno["rounds"][vuelta]["response"]))

    async def disponibilidad(self) -> Disponibilidad:
        grabacion = self._cargar()
        if grabacion is None:
            return Disponibilidad("model_missing", SIN_GRABACION)
        return Disponibilidad(
            "available",
            f"Responde con lo que escribió `{grabacion['model']}` el "
            f"{_fecha(grabacion['recorded_at'])}: el modelo no está en marcha "
            "ahora, y sólo hay respuesta para las consultas grabadas.",
            grabacion["model"],
        )

    def info(self) -> InfoGrabacion | None:
        """Lo que se publica en `GET /agent` para que la pantalla lo diga."""
        grabacion = self._cargar()
        if grabacion is None:
            return None
        return {
            "model": grabacion["model"],
            "recorded_at": grabacion["recorded_at"],
            "commit": grabacion["commit"],
        }

    def ficha(self) -> FichaLLM:
        """La ficha de la grabación (R13.7): opaca, porque el texto lo escribió
        el 27B, y con las limitaciones de reproducir en vez de generar."""
        grabacion = self._cargar()
        tarea = (
            "Reproduce lo que escribió el modelo al grabar la conversación de la "
            "demostración. Las herramientas se ejecutan ahora, y si su resultado "
            "no es el grabado, no reproduce lo grabado. No emite el veredicto: "
            "sale de las herramientas, y las tarjetas se pintan con su resultado, "
            "no con el texto (R13.4)."
        )
        if grabacion is None:
            return {
                "model_id": self.ruta.stem,
                "name": "Respuestas grabadas (no se encuentra la grabación)",
                "task": tarea,
                "type": "opaque",
                "limitations": [SIN_GRABACION],
            }

        modelo = grabacion["model"]
        consultas = "; ".join(f"«{grabado['query']}»" for grabado in grabacion["turns"])
        tomas = grabacion["takes"]
        return {
            "model_id": modelo,
            "name": f"Respuestas grabadas de {modelo}",
            "task": tarea,
            "type": "opaque",
            "limitations": [
                f"No es el modelo respondiendo ahora: es lo que escribió `{modelo}` el {_fecha(grabacion['recorded_at'])}, sobre el commit `{grabacion['commit']}` y con el prompt `{grabacion['prompt']['name']}`.",
                f"Sólo responde a las consultas grabadas: {consultas}. A cualquier otra contesta que no está grabada.",
                f"Se grabaron {tomas['recorded']} tomas de la conversación y se reproduce la {tomas['chosen']}.ª, elegida con una regla publicada antes de grabar (#265): cada turno llama a la herramienta esperada, ninguno acaba vacío ni cortado, y el autor dio cada narración por fiel a su traza.",
                f"Antes de cada vuelta comprueba que el prompt y los resultados de las herramientas son los grabados, con un margen de {MARGEN} en las cifras. Si no lo son, no reproduce lo grabado y lo dice.",
                f"Lo escribió `{modelo}`, de tipo opaco: no explica por qué eligió cada herramienta ni por qué redactó lo que redactó. Sus limitaciones medidas son las de su ficha, que se publica cuando el asistente usa el modelo de verdad.",
            ],
        }


def _ultima_consulta(mensajes: list[Mensaje]) -> int | None:
    """La posición del último mensaje del usuario, o `None` si no hay ninguno."""
    for posicion in range(len(mensajes) - 1, -1, -1):
        if mensajes[posicion]["role"] == "user":
            return posicion
    return None


def _coinciden(
    recibidos: list[tuple[str | None, str]], grabados: list[tuple[str, str]]
) -> bool:
    """Si los resultados que llegan son los grabados, en el mismo orden."""
    return len(recibidos) == len(grabados) and all(
        nombre_recibido == nombre_grabado
        and _mismo_resultado(texto_recibido, texto_grabado)
        for (nombre_recibido, texto_recibido), (nombre_grabado, texto_grabado) in zip(
            recibidos, grabados, strict=True
        )
    )


def _mismo_resultado(recibido: str, grabado: str) -> bool:
    """Dos resultados como los lee el modelo: JSON comparado con el margen en
    las cifras, o, si alguno no es JSON, el texto exacto."""
    try:
        return _parecidos(json.loads(recibido), json.loads(grabado))
    except ValueError:
        return recibido == grabado


def _parecidos(recibido: Any, grabado: Any) -> bool:
    """Iguales a cualquier profundidad, salvo las cifras decimales, que pueden
    diferir en `MARGEN`. Un booleano no es una cifra: `True` no es `1`."""
    if isinstance(recibido, dict) and isinstance(grabado, dict):
        return recibido.keys() == grabado.keys() and all(
            _parecidos(recibido[clave], grabado[clave]) for clave in grabado
        )
    if isinstance(recibido, list) and isinstance(grabado, list):
        return len(recibido) == len(grabado) and all(
            _parecidos(dentro_recibido, dentro_grabado)
            for dentro_recibido, dentro_grabado in zip(recibido, grabado, strict=True)
        )
    if (
        _es_cifra(recibido)
        and _es_cifra(grabado)
        and (isinstance(recibido, float) or isinstance(grabado, float))
    ):
        return abs(recibido - grabado) <= MARGEN + _HOLGURA
    return type(recibido) is type(grabado) and recibido == grabado


def _es_cifra(valor: Any) -> TypeGuard[int | float]:
    return isinstance(valor, int | float) and not isinstance(valor, bool)


def _frase(texto: str) -> Respuesta:
    """Una respuesta fija, sin herramientas ni medidas: no la escribió ningún
    modelo, así que no costó nada que medir."""
    return {
        "content": texto,
        "tool_calls": [],
        "metrics": {
            "prompt_tokens": None,
            "output_tokens": None,
            "load_s": 0.0,
            "total_s": 0.0,
        },
        "cortada": False,
    }


_MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _fecha(dia: date) -> str:
    """Una fecha como se lee: «2 de diciembre de 2026»."""
    return f"{dia.day} de {_MESES[dia.month - 1]} de {dia.year}"
