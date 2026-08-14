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

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, computed_field

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


# --------------------------------------------------------------------------
# Catálogo de herramientas — GET /tools
#
# El catálogo NO es un menú de lanzamiento: es la superficie que responde «qué
# compone este sistema y con qué límites». Por eso cada herramienta puede traer
# su ficha de modelo, y no sólo su nombre y su esquema.
# --------------------------------------------------------------------------


class ServerStatus(str, Enum):
    """Estado de un servidor MCP consultado."""

    OK = "ok"
    UNREACHABLE = "unreachable"  # no respondió, o tardó más que el timeout


class ServerInfo(BaseModel):
    """Un servidor MCP declarado en la configuración, respondiera o no.

    Aparece aunque esté caído: es lo que convierte «seguir operando con los
    restantes y reflejar el estado degradado» en algo observable en vez de en
    una lista más corta sin explicación.
    """

    url: str
    name: str | None = Field(
        default=None,
        description="Nombre que el propio servidor declara en el handshake.",
    )
    status: ServerStatus
    tool_count: int = 0
    detail: str | None = Field(
        default=None, description="Motivo legible cuando no se pudo consultar."
    )


class ToolModelCard(BaseModel):
    """Ficha del modelo que hay detrás de una señal de análisis.

    Es lo que evita que el catálogo enseñe «detect_clickbait_linear — Señales de
    análisis» y esconda que es interpretable, que mide forma y que su F1 cae
    fuera de dominio. Reutiliza los enums de las señales en vez de duplicar
    cadenas sueltas.
    """

    type: SignalType
    dimension: Dimension
    limitations: list[str]


class ToolInfo(BaseModel):
    """Una herramienta del catálogo, con su procedencia y sus metadatos."""

    name: str
    description: str | None = Field(
        default=None, description="Docstring de la tool, tal como la lee el LLM."
    )
    input_schema: dict[str, Any] = Field(
        description=(
            "Esquema JSON de los parámetros, CRUDO. No se aplana: perdería las "
            "restricciones (mínimos, máximos, valores por defecto) que la "
            "interfaz necesita para validar el formulario antes de enviar."
        )
    )

    category: str | None = Field(
        default=None,
        description="Qué tipo de trabajo hace: fuente, señal de análisis o utilidad.",
    )
    integration: str | None = Field(
        default=None,
        description=(
            "Paquete del que procede (nyt, guardian, weather, nlp). None si es "
            "del núcleo y no envuelve ninguna fuente externa."
        ),
    )
    server: str = Field(description="Servidor MCP que la expone.")

    model_card: ToolModelCard | None = Field(
        default=None,
        description="Sólo para las señales de análisis; None para el resto.",
    )


class CatalogResponse(BaseModel):
    """Catálogo completo: qué servidores se consultaron y qué ofrecen."""

    servers: list[ServerInfo]
    tools: list[ToolInfo]

    @computed_field
    @property
    def degraded(self) -> bool:
        """¿Falta algún servidor por responder?

        Va como campo calculado y no como ``@property`` a secas porque la
        interfaz lo necesita EN EL JSON: una propiedad normal no se serializa,
        y obligaría al frontend a recorrer la lista para deducir lo mismo.
        """
        return any(s.status != ServerStatus.OK for s in self.servers)


# --------------------------------------------------------------------------
# Ejecución de una herramienta — POST /tools/{name}/execute
# --------------------------------------------------------------------------


class ExecuteRequest(BaseModel):
    """Parámetros con los que invocar la herramienta.

    Van en un diccionario libre y no en campos declarados porque **cada
    herramienta tiene los suyos**: la forma correcta la publica su
    ``input_schema`` en el catálogo, y contra ese esquema se validan antes de
    ejecutar.
    """

    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Argumentos de la herramienta, según su `input_schema`.",
    )


class ExecuteStatus(str, Enum):
    """Cómo acabó la ejecución."""

    OK = "ok"
    ERROR = "error"  # la herramienta se ejecutó y falló


class ExecuteResponse(BaseModel):
    """Resultado de ejecutar una herramienta.

    Que la herramienta falle **no es un error HTTP**: la petición era válida y
    el servidor la atendió: lo que falló es el análisis. Por eso se responde 200
    con ``status`` en ``error``, igual que una señal caída en ``/analyze`` no
    tumba la respuesta. Los códigos de error se reservan para lo que sí es
    culpa de la petición: 404 si la herramienta no existe, 422 si los argumentos
    no encajan en su esquema.
    """

    tool: str
    server: str
    status: ExecuteStatus

    data: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Salida estructurada de la herramienta, tal como la declara su "
            "`output_schema`. Las que devuelven texto o listas llegan envueltas "
            "en `result`, porque el protocolo sólo deja sin envolver los "
            "objetos."
        ),
    )
    detail: str | None = Field(
        default=None, description="Motivo legible cuando `status` es `error`."
    )


# --------------------------------------------------------------------------
# Historial — GET /history
#
# Se guardan ANÁLISIS, no invocaciones de herramienta: un `POST /analyze` es
# UNA entrada, no cinco. La traza de invocaciones ya vive en los logs.
# --------------------------------------------------------------------------


class HistoryKind(
    str, Enum
):  # Añadir str es un MIXIN!!! (Herencia múltiple para obtener funciones como json.dumps, el cual no funciona con Enum puro)
    """Define qué acción produjo la entrada en el historial."""

    ANALYSIS = "analysis"  # Generado por POST /analyze (señales contrastadas)
    TOOL = "tool"  # Generado por POST /tools/{name}/execute (herramienta suelta)


class Origin(str, Enum):
    """Desde dónde se pidió la entrada en el historial. El prototipo distingue chat y formulario."""

    FORM = "form"
    CHAT = "chat"  # aún no existe: llega con el agente
    API = "api"  # llamada directa, sin interfaz


class HistoryEntry(BaseModel):
    """Una entrada del historial.

    Sobre por qué unos campos son enums y otros cadenas sueltas: los enums
    describen lo que se calcula AHORA, y publican en OpenAPI el conjunto cerrado
    de valores para que el cliente pueda generar un tipo unión. Pero esto son
    **datos leídos de disco, que pudo escribir otra versión del código**, y un
    enum sobre eso es una bomba de relojería: el día que cambie un valor, las
    filas antiguas dejan de validar y `GET /history` devuelve un 500 por una
    entrada de hace seis meses.

    De ahí el reparto: `kind` y `origin` son un conjunto minúsculo, estable y
    bajo nuestro control (si cambiara, se migraría a mano) → enum. `verdict`
    procede de ``OverallVerdict``, un vocabulario de dominio que va a CRECER
    conforme se añadan tipos de clickbait → cadena. `status` se queda en cadena
    porque su significado aún difiere entre tipos —en un análisis es «alguna
    señal funcionó», en una herramienta es «no falló»— y eso se replantea al
    llegar el filtrado (#103).
    """

    id: int
    created_at: datetime
    kind: HistoryKind
    origin: Origin

    headline: str | None = Field(
        default=None, description="Titular analizado. Nulo en ejecuciones sueltas."
    )
    tool: str | None = Field(
        default=None, description="Herramienta invocada. Nulo en análisis completos."
    )
    verdict: str | None = Field(
        default=None, description="Veredicto global. Nulo en ejecuciones sueltas."
    )
    status: str

    payload: dict[str, Any] = Field(
        description=(
            "La respuesta COMPLETA que se devolvió en su momento. Es lo que "
            "permite volver a mostrar el resultado sin reejecutar — que además "
            "de costar ~20 s podría dar otro resultado, porque las señales "
            "remotas no son deterministas."
        )
    )


class HistoryPage(BaseModel):
    """Una página del historial, en orden cronológico inverso."""

    items: list[HistoryEntry]
    total: int = Field(
        description=(
            "Entradas totales, no las de esta página. La interfaz lo necesita "
            "para paginar; sin él sólo puede saber si hay más pidiendo la "
            "siguiente."
        )
    )
    limit: int
    offset: int
