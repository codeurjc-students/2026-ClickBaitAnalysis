"""El idioma de un texto: inglés, español u otro (issue #229).

POR QUÉ EXISTE

Hasta #229 un titular en español se analizaba como si fuera inglés, y el sistema
no lo decía: en TA1C (`evaluation/eval_ta1c.py`) daba «factual» al 80 % de los
teasers y reconocía el 1,9 % del clickbait. Saber en qué idioma está el titular
es lo primero para no dar un veredicto que no se puede sostener, y después para
mandar cada titular a las señales de su idioma.

POR QUÉ VIVE EN `core/`

El criterio de `core/` es «¿lo usa más de una capa y no sabe nada del
clickbait?». Lo usan `analysis/` (el orquestador y el contrato) e
`integrations/` (las herramientas MCP), y decidir el idioma de un texto no sabe
nada de clickbait. Lo que sí sabe del dominio —qué idiomas admite cada señal y
qué se le dice a quien manda otro— vive junto a las señales.

CÓMO DECIDE

Cuenta las **palabras funcionales** de cada idioma: artículos, preposiciones,
pronombres, conjunciones. Son las más frecuentes de una lengua y no dependen del
tema, así que aparecen hasta en un titular corto. Al español le suma lo que el
inglés no tiene: la eñe, las tildes y los signos de apertura (¿ ¡).

- Se quitan de las listas las palabras que se confunden: las que existen en los
  dos idiomas (*a*, *no*, *me*, *he*, *son*, *has*), las que un titular inglés
  escribe en mayúsculas como sigla y aquí llegan en minúsculas (*un* por «UN»,
  *mit* por «MIT», *est* por «EST»), y las compartidas con otra lengua cercana
  (*le*, *les*, *dos*, *das*).
- Para «otro idioma» hay listas cortas de francés, portugués, italiano y alemán,
  sólo con palabras que no están en las del inglés ni del español, y las letras
  que el español no usa (à, è, ç, ã, ä, ö, ß…). Esas letras **sólo cuentan si
  hay al menos una palabra de esas listas**: solas, casi siempre son un nombre
  propio en un titular inglés («Kimi Räikkönen», «São Paulo»).
- Las tildes del español, en cambio, **cuentan aunque no haya ninguna palabra
  española**. Exigirla quitaba falsas alarmas en inglés (de 38 a 27 en
  Chakraborty `train`), pero dejaba escapar más español (de 3 a 11 en TA1C
  `train`), y los dos errores no pesan igual: un titular inglés tomado por
  español se queda sin veredicto con el motivo a la vista; uno español tomado
  por inglés recibe un veredicto equivocado y en silencio, que es lo que #229
  arregla.
- **Sin ninguna prueba, inglés.** El sistema nació para inglés, y un titular sin
  palabras funcionales («Obama Wins Election») es mucho más probable que sea
  inglés que otra cosa. Marcarlo como extranjero le quitaría el análisis a quien
  siempre lo tuvo.

Las listas se afinan mirando sólo los conjuntos de entrenamiento (Chakraborty
`train`, `train170331` de Webis-17 y TA1C `train`); la regla de #229 se aplica en
los de elección (`evaluation/eval_idioma.py`), para no ajustar el detector al
examen.

LÍMITES

- Un titular inglés con un nombre propio con tilde y sin palabras funcionales
  («Peña Nieto wins») puede salir español.
- Portugués, italiano o francés muy cortos, sin ninguna palabra de sus listas,
  pueden salir español por las tildes, o inglés por no tener pruebas («Governo
  anuncia novas medidas para a economia» sale español). Para ellos no hay
  corpus con el que medirlo: se prueban con ejemplos.
- «che» es italiano, pero también se dice en Argentina: «Che Guevara» sale
  «otro idioma».
"""

import re
from typing import Literal

Idioma = Literal["en", "es", "und"]

INGLES: Idioma = "en"
ESPANOL: Idioma = "es"
# «und» es «indeterminado» en BCP 47: vale también para el atributo `lang`.
INDETERMINADO: Idioma = "und"

NOMBRES: dict[Idioma, str] = {
    INGLES: "inglés",
    ESPANOL: "español",
    INDETERMINADO: "otro idioma",
}

# Sólo letras, tildes incluidas: ni dígitos ni guiones bajos.
_PALABRA = re.compile(r"[^\W\d_]+")
# Lo que el español tiene y el inglés no. La «ü» no: también es alemana.
_RASGOS_DEL_ESPANOL = re.compile(r"[ñáéíóú¿¡]")
# Letras de francés, portugués, italiano y alemán que el español no usa.
_RASGOS_DE_OTROS = re.compile(r"[àèìòùâêîôûçãõäöß]")

_FUNCIONALES_INGLES = frozenset(
    "the of to and in is for on with that this these those you your are was were "
    "be been by from at as it its how why what who will have after about into an "
    "or but not can more they their we our his her she him than when out up just "
    "all if would could should there here which may".split()
)
_FUNCIONALES_ESPANOL = frozenset(
    "el la los las de del que en y por para con una es se su sus lo al como más "
    "pero este esta estos estas sobre tras entre sin ya fue hay qué cómo cuál "
    "cuándo dónde muy también porque desde hasta ha han nos".split()
)
# Francés, portugués, italiano y alemán, sólo con lo que no está arriba.
_FUNCIONALES_OTROS = frozenset(
    "des du et une dans avec qui sur pas au aux cette ces sont mais ne vous nous ce "
    "não uma da ao aos em um você mais na pelo pela foi às "
    "il gli della delle dei che nel nella sono alla anche questo di sul ma più "
    "der und ist nicht für auf ein eine dem von zu sich auch wird sie wie nach aus "
    "bei über".split()
)


def contar(texto: str) -> dict[str, int]:
    """Las pruebas de cada idioma en el texto: cuántas palabras de cada lista, y
    además los rasgos de cada uno —en el español, eñe, tildes y ¿ ¡, siempre; en
    los otros, sus letras, sólo si ya hay alguna palabra suya—.

    Se expone aparte de `detectar` para poder enseñar POR QUÉ un texto salió del
    idioma que salió, que es lo que hace falta para leer sus fallos.
    """
    minusculas = texto.lower()
    palabras = _PALABRA.findall(minusculas)
    otros = sum(palabra in _FUNCIONALES_OTROS for palabra in palabras)
    if otros:
        otros += len(_RASGOS_DE_OTROS.findall(minusculas))
    return {
        INGLES: sum(palabra in _FUNCIONALES_INGLES for palabra in palabras),
        ESPANOL: sum(palabra in _FUNCIONALES_ESPANOL for palabra in palabras)
        + len(_RASGOS_DEL_ESPANOL.findall(minusculas)),
        INDETERMINADO: otros,
    }


def detectar(texto: str) -> Idioma:
    """El idioma del texto: el que más pruebas tenga, e inglés si no hay ninguna."""
    pruebas = contar(texto)
    if pruebas[INDETERMINADO] > max(pruebas[INGLES], pruebas[ESPANOL]):
        return INDETERMINADO
    if pruebas[ESPANOL] > pruebas[INGLES]:
        return ESPANOL
    return INGLES
