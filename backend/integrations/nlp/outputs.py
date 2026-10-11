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

**El idioma (#230).** Cada ficha es de un idioma (``language``): una señal
tiene una por cada idioma en que la analiza un modelo declarado. Y cada salida
de señal dice en qué idioma se analizó el titular, también ``language``: la
añaden quienes ejecutan la señal —cada herramienta suelta y el orquestador—,
porque los detectores no saben de idiomas. Lo lee el historial, que guarda la
salida de cada herramienta y no sabía en qué idioma pintar su titular.

Es obligatorio, y no ``NotRequired``, por dos cosas medidas al escribirlo. Una:
FastMCP escribe como ``null`` un campo opcional que falta, y después lo rechaza
contra su propio esquema («None is not one of ['en', 'es', 'und']»). Otra: el
contrato publica estas formas también para el ``data`` de ``/analyze``, así que
lo que digan tiene que ser cierto en las dos rutas.
"""

from typing import TypedDict

from backend.core.idioma import Idioma


class Etiqueta(TypedDict):
    """Salida de un clasificador: la etiqueta ganadora y su confianza."""

    label: str
    score: float
    language: Idioma


class Pista(TypedDict):
    """Una marca léxica encontrada en el titular, y dónde aparece."""

    category: str
    cue: str
    span: list[int]  # [inicio, fin] sobre el titular original


class SalidaLexica(TypedDict):
    """Salida del detector por reglas. La evidencia ES la explicación (R3.8).

    Lleva el ``threshold`` —cuántas pistas hacen falta— desde #93, cuando pasó a
    configurarse: sin él, la interfaz tendría que dar por hecho que basta una, y
    con otro umbral diría algo falso junto a las mismas pistas.
    """

    score: int
    is_clickbait: bool
    threshold: float
    matches: list[Pista]
    headline: str
    language: Idioma


class SalidaLineal(TypedDict):
    """Salida del modelo lineal interpretable.

    ``top_cues`` empareja cada cue con su contribución al veredicto (peso ×
    frecuencia); es la explicación intrínseca del modelo.

    Lleva el ``threshold`` desde #231, cuando dejó de ser 0,5: sin él, quien
    leyera «probabilidad 0,41» junto a «clickbait» pensaría que no cuadra.
    """

    is_clickbait: bool
    probability: float
    threshold: float
    top_cues: list[tuple[str, float]]
    headline: str
    language: Idioma


class SalidaIncoherencia(TypedDict):
    """Salida del contraste titular↔cuerpo.

    Devuelve los textos comparados además de la similitud: sin ellos, el
    resultado no es verificable por quien lo lee.

    Y devuelve el ``threshold`` contra el que se comparó (#133), que es lo que
    hace auditable la decisión: sin él, ``incoherent`` es un veredicto que hay
    que creerse. Es la única señal híbrida —decisión transparente sobre un rasgo
    opaco—, así que enseñar el corte no es un adorno, es la mitad de su tesis.
    """

    similarity: float
    incoherent: bool
    threshold: float
    headline: str
    content: str
    language: Idioma


class FichaModelo(TypedDict):
    """Una entrada de la divulgación de modelos.

    Tres campos parecen lo mismo y no lo son, así que conviene fijarlos aquí:
    ``signal`` es el nombre de la tool MCP, ``model_id`` el identificador en
    HuggingFace y ``name`` la etiqueta que lee una persona. Cada uno lo consume
    alguien distinto —el orquestador, la llamada al backend y la interfaz—, y
    cuando eran un solo campo había que elegir a quién servir mal (#116).

    ``model_id`` es ``None`` en las señales que no son un modelo descargable —el
    léxico y el lineal—, y ese ``None`` es información, no un hueco.

    ``revision`` es el commit del Hub de esos pesos (#234), entero: las medidas
    de la ficha son de ellos, y la imagen hornea justo ése. Sin él, un autor
    que subiera pesos nuevos cambiaría el modelo servido en la siguiente
    construcción, con las medidas del anterior publicadas. ``None`` donde no
    hay modelo descargable, y en un modelo puesto por configuración, que no
    se fija.
    """

    signal: str
    # El idioma de los titulares que analiza ESTE modelo (#230). La dimensión
    # y el tipo describen el hueco y no cambian con él; el modelo, sí.
    language: Idioma
    model_id: str | None
    revision: str | None
    name: str
    task: str
    type: str
    dimension: str
    limitations: list[str]
    backend: str
