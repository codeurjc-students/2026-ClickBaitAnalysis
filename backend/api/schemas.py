"""Contrato de la API REST: catálogo, ejecución e historial.

Lo que hay aquí describe **el sistema que sirve el análisis** —qué servidores MCP
están conectados, qué herramientas exponen, cómo se ejecuta una y qué quedó
registrado—, no qué es el clickbait. Ese vocabulario vive en
``backend/analysis/domain.py``.

El criterio para saber dónde va un tipo: **si borraras la API REST y el servidor
MCP y dejaras sólo una función de Python que analiza titulares, ¿seguiría
haciendo falta?** Si la respuesta es sí, es dominio y va en ``analysis/``; si es
no, es contrato y va aquí.

La dependencia va en **un solo sentido**: este fichero importa de ``analysis/``,
nunca al revés. El dominio no sabe que lo están sirviendo, y por eso puede
servirse también por MCP. El día que ``analysis/`` necesite importar de aquí,
algo está mal colocado.

(``ToolModelCard`` ilustra la dirección permitida: se queda aquí —es el catálogo
hablando de sus componentes, o sea sistema— pero usa ``SignalType`` y
``Dimension``, que son dominio.)
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field

from backend.analysis.domain import Dimension, SignalType

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


class RetentionPolicy(BaseModel):
    """Política de retención vigente, para que la interfaz no la cablee.

    Va en la respuesta porque la pantalla la necesita para dos cosas, y las dos
    son de usabilidad, no de adorno:

    1. **Explicar por qué faltan análisis viejos.** La poda es invisible, y eso
       es justo el problema: quien analizó algo hace cuarenta días y no lo
       encuentra no piensa «se habrá podado», piensa que la aplicación ha perdido
       sus datos. Un borrado silencioso se lee como un fallo.
    2. **Acotar el selector de fechas.** Un calendario libre que permita pedir
       «hace seis meses» y devuelva siempre vacío es una mala experiencia.

    Y va aquí en vez de como constantes en Angular para que esos números salgan
    de la configuración REAL: cableados, se desincronizarían el día que cambie
    el `.env` y la pantalla seguiría prometiendo 30 días.
    """

    max_entries: int = Field(description="Entradas conservadas. 0 = sin límite.")
    max_days: int = Field(description="Días conservados. 0 = sin límite.")


class HistoryPage(BaseModel):
    """Una página del historial, en orden cronológico inverso."""

    items: list[HistoryEntry]
    total: int = Field(
        description=(
            "Entradas totales que casan con el filtro, no las de esta página. La "
            "interfaz lo necesita para paginar; sin él sólo puede saber si hay "
            "más pidiendo la siguiente. Ojo con leerlo como «cuántos análisis he "
            "hecho»: con retención activa es «cuántos se conservan»."
        )
    )
    limit: int
    offset: int
    retention: RetentionPolicy
