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

    .venv/bin/python -m backend.evaluation.eval_idioma --train   # para afinar
    .venv/bin/python -m backend.evaluation.eval_idioma           # la regla
"""

import sys
from collections import Counter
from collections.abc import Callable

from backend.core import idioma
from backend.evaluation.eval_external import load_external
from backend.evaluation.splits import load_split

MAXIMO_FUERA_DEL_INGLES = 0.01
MINIMO_DEL_ESPANOL = 0.95
FALLOS_A_ENSEÑAR = 25

Conjunto = tuple[str, Callable[[], list[str]], idioma.Idioma]


def _titulares(split: str) -> Callable[[], list[str]]:
    return lambda: [titular for titular, _ in load_split(split)]


CONJUNTOS_TRAIN: list[Conjunto] = [
    ("Chakraborty train", _titulares("train"), idioma.INGLES),
    (
        "Webis-17 train170331",
        lambda: [titular for titular, _, _ in load_external("train170331")],
        idioma.INGLES,
    ),
    ("TA1C train", _titulares("ta1c_train"), idioma.ESPANOL),
]
CONJUNTOS_REGLA: list[Conjunto] = [
    ("Chakraborty dev", _titulares("dev"), idioma.INGLES),
    ("webis_dev", _titulares("webis_dev"), idioma.INGLES),
    ("TA1C validation", _titulares("ta1c_validation"), idioma.ESPANOL),
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
    nombre: str, titulares: list[str], esperado: idioma.Idioma
) -> dict[str, float]:
    """El reparto de idiomas detectados y los fallos, con sus pruebas."""
    detectados = [idioma.detectar(titular) for titular in titulares]
    reparto = Counter(detectados)
    proporciones = {
        codigo: reparto[codigo] / len(titulares)
        for codigo in (idioma.INGLES, idioma.ESPANOL, idioma.INDETERMINADO)
    }
    print(
        f"\n== {nombre}: {len(titulares)} titulares, se espera «{esperado}» · "
        + " · ".join(f"{codigo} {parte:.2%}" for codigo, parte in proporciones.items())
    )
    fallos = [
        (titular, detectado)
        for titular, detectado in zip(titulares, detectados, strict=True)
        if detectado != esperado
    ]
    for titular, detectado in fallos[:FALLOS_A_ENSEÑAR]:
        print(f"   {detectado} {idioma.contar(titular)} · {titular[:110]}")
    if len(fallos) > FALLOS_A_ENSEÑAR:
        print(f"   … y {len(fallos) - FALLOS_A_ENSEÑAR} fallos más")
    return proporciones


def afinar() -> None:
    """Los conjuntos de entrenamiento: con esto se afinan las listas."""
    for nombre, cargar, esperado in CONJUNTOS_TRAIN:
        medir(nombre, cargar(), esperado)


def regla() -> None:
    """Los conjuntos de elección, con la regla de #229."""
    cumple = True
    for nombre, cargar, esperado in CONJUNTOS_REGLA:
        proporciones = medir(nombre, cargar(), esperado)
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
    else:
        regla()
    ejemplos()
