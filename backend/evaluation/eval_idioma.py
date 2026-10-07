"""¿Distingue `core/idioma.detectar` un titular inglés de uno español? (issue #229)

La regla se publicó en #229 antes de medir
(https://github.com/codeurjc-students/2026-ClickBaitAnalysis/issues/229#issuecomment-6039059405):

1. en inglés —Chakraborty `dev` (6.400) y `webis_dev` (3.896)—, como mucho un
   1 % de los titulares detectados como otro idioma, en cada uno;
2. en español —TA1C `validation` (700)—, al menos un 95 % detectado como
   español.

Para no ajustar el detector al examen, las listas de palabras se afinan mirando
sólo los conjuntos de entrenamiento (`--train`: Chakraborty `train`,
`train170331` de Webis-17 y TA1C `train`), y la regla se aplica a los de
elección. Cada fallo sale con sus pruebas (`idioma.contar`), que es lo que dice
por qué falló.

Para otros idiomas no hay corpus: unos titulares escritos a mano en francés,
portugués, italiano y alemán, que son ejemplos y no una medida.

`--cuerpos` aplica la misma regla a cuerpos de noticia (los de `webis_dev` y
los de TA1C `validation`): desde #229 la puerta mira también el cuerpo, porque
la incoherencia compara titular y cuerpo con un modelo inglés, y el detector
se afinó con titulares. Esa regla también se publicó antes de medir
(https://github.com/codeurjc-students/2026-ClickBaitAnalysis/issues/229#issuecomment-6045492294).

    .venv/bin/python -m backend.evaluation.eval_idioma --train     # para afinar
    .venv/bin/python -m backend.evaluation.eval_idioma             # la regla
    .venv/bin/python -m backend.evaluation.eval_idioma --cuerpos   # en cuerpos
"""

import gzip
import json
import sys
from collections import Counter
from collections.abc import Callable

from backend.core import idioma

# `load_split`, `load_external` y los cargadores de cuerpos se importan dentro
# de quien los usa: sus módulos importan scikit-learn, que el CI no instala, y
# `tests/core/test_idioma.py` importa éste por sus ejemplos (#229).

MAXIMO_FUERA_DEL_INGLES = 0.01
MINIMO_DEL_ESPANOL = 0.95
FALLOS_A_ENSEÑAR = 25

Conjunto = tuple[str, Callable[[], list[str]], idioma.Idioma]


def _titulares(split: str) -> Callable[[], list[str]]:
    def leer() -> list[str]:
        from backend.evaluation.splits import load_split

        return [titular for titular, _ in load_split(split)]

    return leer


def _titulares_de_webis(nombre: str) -> Callable[[], list[str]]:
    def leer() -> list[str]:
        from backend.evaluation.eval_external import load_external

        return [titular for titular, _, _ in load_external(nombre)]

    return leer


CONJUNTOS_TRAIN: list[Conjunto] = [
    ("Chakraborty train", _titulares("train"), idioma.INGLES),
    ("Webis-17 train170331", _titulares_de_webis("train170331"), idioma.INGLES),
    ("TA1C train", _titulares("ta1c_train"), idioma.ESPANOL),
]
CONJUNTOS_REGLA: list[Conjunto] = [
    ("Chakraborty dev", _titulares("dev"), idioma.INGLES),
    ("webis_dev", _titulares("webis_dev"), idioma.INGLES),
    ("TA1C validation", _titulares("ta1c_validation"), idioma.ESPANOL),
]


def _cuerpos_de_webis(split: str) -> Callable[[], list[str]]:
    """Los cuerpos de los titulares de un split de Webis, sin los vacíos."""

    def leer() -> list[str]:
        from backend.evaluation.eval_incoherencia import CUERPOS
        from backend.evaluation.splits import SPLITS_DIR

        with open(SPLITS_DIR / f"{split}.jsonl", encoding="utf-8") as fichero:
            ids = [json.loads(linea)["id"] for linea in fichero]
        with gzip.open(CUERPOS, "rt", encoding="utf-8") as fichero:
            cuerpos = {
                registro["id"]: " ".join(registro["paragraphs"]).strip()
                for registro in map(json.loads, fichero)
            }
        return [
            cuerpos[identificador]
            for identificador in ids
            if cuerpos.get(identificador)
        ]

    return leer


def _cuerpos_de_ta1c(parte: str) -> Callable[[], list[str]]:
    """Los cuerpos de los artículos de una parte de TA1C, sin los vacíos."""

    def leer() -> list[str]:
        from backend.evaluation.eval_ta1c import cargar

        return [fila["cuerpo"] for fila in cargar(parte) if fila["cuerpo"].strip()]

    return leer


# Los mismos conjuntos de elección que los titulares, con sus cuerpos.
CONJUNTOS_CUERPOS: list[Conjunto] = [
    ("webis_dev, cuerpos", _cuerpos_de_webis("webis_dev"), idioma.INGLES),
    ("TA1C validation, cuerpos", _cuerpos_de_ta1c("validation"), idioma.ESPANOL),
]

# Escritos para esto, no sacados de ningún corpus: sirven para ver qué hace el
# detector, no para medirlo.
EJEMPLOS_DE_OTROS_IDIOMAS = [
    ("francés", "Le gouvernement annonce une nouvelle réforme des retraites"),
    ("francés", "Ce que les médecins ne vous disent pas sur le sommeil"),
    ("francés", "Incendie dans un entrepôt près de Lyon"),
    ("portugués", "Governo anuncia novas medidas para a economia"),
    ("portugués", "Você não vai acreditar no que este cão fez"),
    ("portugués", "Chuva forte deixa cidades em alerta no sul do país"),
    ("italiano", "Il governo approva la nuova legge sul lavoro"),
    ("italiano", "Non crederai mai a cosa ha fatto questo cane"),
    ("italiano", "Scoperta una nuova specie di rana nella foresta"),
    ("alemán", "Die Regierung kündigt neue Maßnahmen für die Wirtschaft an"),
    ("alemán", "Was Ärzte Ihnen nicht über Schlaf sagen"),
    ("alemán", "Neue Studie zeigt Folgen des Klimawandels"),
]


def medir(
    nombre: str,
    textos: list[str],
    esperado: idioma.Idioma,
    unidad: str = "titulares",
) -> dict[str, float]:
    """El reparto de idiomas detectados y los fallos, con sus pruebas."""
    detectados = [idioma.detectar(texto) for texto in textos]
    reparto = Counter(detectados)
    proporciones = {
        codigo: reparto[codigo] / len(textos)
        for codigo in (idioma.INGLES, idioma.ESPANOL, idioma.INDETERMINADO)
    }
    print(
        f"\n== {nombre}: {len(textos)} {unidad}, se espera «{esperado}» · "
        + " · ".join(f"{codigo} {parte:.2%}" for codigo, parte in proporciones.items())
    )
    fallos = [
        (texto, detectado)
        for texto, detectado in zip(textos, detectados, strict=True)
        if detectado != esperado
    ]
    for texto, detectado in fallos[:FALLOS_A_ENSEÑAR]:
        print(f"   {detectado} {idioma.contar(texto)} · {texto[:110]}")
    if len(fallos) > FALLOS_A_ENSEÑAR:
        print(f"   … y {len(fallos) - FALLOS_A_ENSEÑAR} fallos más")
    return proporciones


def afinar() -> None:
    """Los conjuntos de entrenamiento: con esto se afinan las listas."""
    for nombre, cargar, esperado in CONJUNTOS_TRAIN:
        medir(nombre, cargar(), esperado)


def regla(
    conjuntos: list[Conjunto] = CONJUNTOS_REGLA, unidad: str = "titulares"
) -> None:
    """Los conjuntos de elección, con la regla de #229."""
    cumple = True
    for nombre, cargar, esperado in conjuntos:
        proporciones = medir(nombre, cargar(), esperado, unidad)
        if esperado == idioma.INGLES:
            fuera = 1 - proporciones[idioma.INGLES]
            bien = fuera <= MAXIMO_FUERA_DEL_INGLES
            print(
                f"   → fuera del inglés {fuera:.2%} (máximo {MAXIMO_FUERA_DEL_INGLES:.0%}): {'cumple' if bien else 'NO cumple'}"
            )
        else:
            bien = proporciones[idioma.ESPANOL] >= MINIMO_DEL_ESPANOL
            print(
                f"   → español {proporciones[idioma.ESPANOL]:.2%} (mínimo {MINIMO_DEL_ESPANOL:.0%}): {'cumple' if bien else 'NO cumple'}"
            )
        cumple = cumple and bien
    print(f"\n=> la regla {'SE CUMPLE' if cumple else 'NO SE CUMPLE'}")


def ejemplos() -> None:
    print(
        "\n== otros idiomas: ejemplos escritos a mano, no una medida (se espera «und»)"
    )
    for lengua, titular in EJEMPLOS_DE_OTROS_IDIOMAS:
        print(
            f"   {idioma.detectar(titular):3} {idioma.contar(titular)} · {lengua}: {titular}"
        )


if __name__ == "__main__":
    if "--train" in sys.argv:
        afinar()
    elif "--cuerpos" in sys.argv:
        regla(CONJUNTOS_CUERPOS, unidad="cuerpos")
    else:
        regla()
    ejemplos()
