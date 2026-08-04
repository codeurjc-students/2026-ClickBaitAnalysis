"""Contrato de la API REST (R4).

Estos modelos definen la respuesta de ``POST /analyze``, el endpoint que orquesta
las señales de clickbait. Es el contrato más importante del sistema porque lo
consumen **tres** sitios: el formulario de análisis, las tarjetas embebidas en el
chat y el historial. Se diseña una vez y sirve para los tres.

Tres principios lo gobiernan:

1. **Envoltorio uniforme por señal.** Las señales son una LISTA de objetos con la
   misma forma, no un objeto con un campo por señal. Así el frontend itera y
   pinta tarjetas sin conocerlas de antemano: añadir una quinta señal no obliga a
   tocar Angular. Es el mismo desacople que en el catálogo.

2. **El estado va por señal, no global.** Un único campo ``status`` cubre dos
   situaciones que, desde el punto de vista de la respuesta, son la misma —esa
   señal no tiene resultado, pero las demás sí—: que falten datos de entrada
   (``no_aplicable``: la incoherencia necesita el cuerpo) y que la ejecución
   falle (``error``: ~1 de cada 5 llamadas a HuggingFace da timeout, medido en la
   Épica 4). ``/analyze`` NO devuelve error global mientras alguna señal
   funcione: perder tres análisis correctos porque el cuarto falló sería el mismo
   error que evita R6.13.

3. **Veredicto por dimensiones, no por mayoría.** Las señales miden cosas
   distintas (forma vs engaño), así que promediarlas produce un veredicto
   engañoso: tres señales de forma de acuerdo no significan que el titular mienta.
   La dimensión de cada señal se lee de ``MODEL_CARDS`` (R3.9), no se cablea aquí.

   El tono se presenta como una señal más, pero no vota: alejarse de la
   objetividad no es lo mismo que hacer clickbait, y cuánto pesa eso es juicio
   de quien lee. No hace falta ningún caso especial para conseguirlo —
   simplemente no emite veredicto, igual que una señal que ha fallado.
"""

from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

# Recorta antes de medir. Con un simple `min_length=1`, un titular de un solo
# espacio pasa la validación —mide 1 carácter— y llega hasta las señales, que
# fallan una a una: la respuesta sería un 200 con veredicto `sin_datos` en vez
# del 422 que corresponde a una petición inválida. Pydantic aplica
# `strip_whitespace` antes que `min_length`, así que el blanco se rechaza aquí.
NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SignalStatus(str, Enum):
    """Por qué una señal tiene o no resultado."""

    OK = "ok"
    NO_APLICABLE = "no_aplicable"  # faltan datos de entrada (p. ej. el cuerpo)
    ERROR = "error"  # la ejecución falló (timeout, proveedor caído...)


class Dimension(str, Enum):
    """Qué mide una señal. Determina cómo se agrupan los veredictos."""

    FORMA = "forma"  # sensacionalismo en la redacción
    ENGANO = "engano"  # el titular promete algo que el cuerpo no cumple
    TONO = "tono"  # carga emocional; contexto que se muestra, no veredicto


class SignalType(str, Enum):
    """Naturaleza del modelo. Se muestra como badge en la interfaz."""

    INTERPRETABLE = "interpretable"
    HIBRIDO = "híbrido"
    OPACO = "opaco"


class SignalResult(BaseModel):
    """Resultado de UNA señal, con el mismo envoltorio sea cual sea (principio 1)."""

    name: str = Field(description="Nombre de la herramienta MCP que la produjo.")
    status: SignalStatus
    dimension: Dimension
    type: SignalType = Field(
        description="Naturaleza del modelo, para el badge de la UI."
    )

    is_clickbait: bool | None = Field(
        default=None,
        description=(
            "Veredicto de esta señal, o None si no aporta ninguno: porque no "
            "pudo ejecutarse, o porque por naturaleza no lo emite (el tono). El "
            "agregado ignora los None en ambos casos; ``status`` distingue cuál "
            "de los dos ha sido."
        ),
    )
    data: dict[str, Any] | None = Field(
        default=None,
        description=(
            "JSON CRUDO devuelto por la herramienta, sin aplanar. Es lo que "
            "alimenta las tarjetas de explicabilidad (spans, top_cues, "
            "similitud...). No se transforma aquí para no perder información "
            "que la interfaz pueda necesitar."
        ),
    )
    detail: str | None = Field(
        default=None,
        description=(
            "Motivo legible cuando no hay resultado: «requiere el cuerpo de la "
            "noticia», «el proveedor no respondió». Permite pintar la tarjeta en "
            "gris explicando por qué, en vez de omitirla sin más."
        ),
    )


class DimensionVerdict(BaseModel):
    """Veredicto agregado de las señales que miden lo mismo (principio 3).

    Solo aparecen las dimensiones en las que alguna señal llegó a emitir
    veredicto. Si ninguna lo hizo —fallaron, faltaba el cuerpo, o la dimensión
    no vota— la dimensión no se incluye, en vez de añadir un objeto vacío que la
    interfaz tendría que aprender a ignorar. El motivo no se pierde: está en la
    tarjeta de cada señal, que es donde el usuario lo lee.
    """

    dimension: Dimension
    is_clickbait: bool | None = Field(
        default=None,
        description=(
            "None si las señales de esta dimensión se contradicen: no se "
            "promedian ni se resuelven por mayoría, se declara la discrepancia."
        ),
    )
    contributing: list[str] = Field(
        default_factory=list,
        description="Señales que han contribuido a este veredicto.",
    )


class OverallVerdict(str, Enum):
    """Etiqueta única, para listados compactos como el historial.

    Se deriva de las dimensiones con una jerarquía explícita —el engaño pesa más
    que la forma— en lugar de por mayoría de señales.
    """

    ENGANOSO = "enganoso"  # hay engaño: el cuerpo no corresponde al titular
    CLICKBAIT_DE_FORMA = "clickbait_de_forma"  # sensacionalista, pero sin engañar
    FACTUAL = "factual"
    AMBIGUO = "ambiguo"  # las señales de una misma dimensión se contradicen
    SIN_DATOS = "sin_datos"  # ninguna señal llegó a emitir veredicto


class AnalyzeRequest(BaseModel):
    headline: NonBlankStr = Field(description="Titular a analizar (en inglés).")
    content: str | None = Field(
        default=None,
        description=(
            "Cuerpo o teaser. Opcional: sin él, la señal de incoherencia queda "
            "en 'no_aplicable' y no se puede evaluar la dimensión de engaño."
        ),
    )


class AnalyzeResponse(BaseModel):
    headline: str
    content: str | None = None

    signals: list[SignalResult]
    dimensions: list[DimensionVerdict]
    verdict: OverallVerdict

    @property
    def has_any_result(self) -> bool:
        """¿Alguna señal llegó a ejecutarse? Si no, la respuesta es informativa
        (dice por qué falló cada una) pero no hay análisis que mostrar."""
        return any(s.status == SignalStatus.OK for s in self.signals)
