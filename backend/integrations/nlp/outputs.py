"""Tipos de salida de las tools NLP, para que MCP publique su ``outputSchema``.

Sin un tipo **declarado** en la firma, MCP no genera esquema de salida: se
comprobó que anotar ``-> dict`` a secas deja ``outputSchema`` en ``None`` y
``structuredContent`` vacío, y que ``-> str`` con ``json.dumps`` obliga al
consumidor a parsear texto a ciegas.

Con estos tipos, el catálogo publica qué devuelve cada herramienta y el cliente
recibe el objeto ya estructurado. Son ``TypedDict`` y no modelos Pydantic
porque las capas de cliente ya devuelven diccionarios: así no hay que convertir
nada, sólo declarar la forma que ya tienen.

**No se declara aquí el éxito o el fallo.** Ese eje lo lleva el protocolo, con
``isError``: las tools **lanzan** cuando algo va mal, en vez de devolver un
mensaje de error por el mismo canal que un resultado válido.
"""

from typing import TypedDict


class Etiqueta(TypedDict):
    """Salida de un clasificador: la etiqueta ganadora y su confianza."""

    label: str
    score: float


class Pista(TypedDict):
    """Una marca léxica encontrada en el titular, y dónde aparece."""

    category: str
    cue: str
    span: list[int]  # [inicio, fin] sobre el titular original


class SalidaLexica(TypedDict):
    """Salida del detector por reglas. La evidencia ES la explicación (R3.8)."""

    score: int
    is_clickbait: bool
    matches: list[Pista]
    headline: str


class SalidaLineal(TypedDict):
    """Salida del modelo lineal interpretable.

    ``top_cues`` empareja cada cue con su contribución al veredicto (peso ×
    frecuencia); es la explicación intrínseca del modelo.
    """

    is_clickbait: bool
    probability: float
    top_cues: list[tuple[str, float]]
    headline: str


class SalidaIncoherencia(TypedDict):
    """Salida del contraste titular↔cuerpo.

    Devuelve los textos comparados además de la similitud: sin ellos, el
    resultado no es verificable por quien lo lee.
    """

    similarity: float
    incoherent: bool
    headline: str
    content: str


class FichaModelo(TypedDict):
    """Una entrada de la divulgación de modelos.

    Tres campos parecen lo mismo y no lo son, así que conviene fijarlos aquí:
    ``signal`` es el nombre de la tool MCP, ``model_id`` el identificador en
    HuggingFace y ``name`` la etiqueta que lee una persona. Cada uno lo consume
    alguien distinto —el orquestador, la llamada al backend y la interfaz—, y
    cuando eran un solo campo había que elegir a quién servir mal (#116).

    ``model_id`` es ``None`` en las señales que no son un modelo descargable —el
    léxico y el lineal—, y ese ``None`` es información, no un hueco.
    """

    signal: str
    model_id: str | None
    name: str
    task: str
    type: str
    dimension: str
    limitations: list[str]
    backend: str
