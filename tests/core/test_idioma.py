"""El detector de idioma (#229): qué decide, y dónde se equivoca a sabiendas.

Los casos de inglés y de español tienen la forma de titulares de verdad; los de
otros idiomas son los doce ejemplos de `evaluation/eval_idioma.py`, con los que
se midió el detector. Los límites que declara el docstring de `core/idioma.py`
se fijan aquí también: si un cambio arregla alguno, el test falla para que el
docstring se corrija con él.
"""

from typing import get_args

import pytest

from backend.core.idioma import (
    ESPANOL,
    INDETERMINADO,
    INGLES,
    NOMBRES,
    Idioma,
    contar,
    detectar,
)
from backend.evaluation.eval_idioma import EJEMPLOS_DE_OTROS_IDIOMAS

# Los límites del docstring, con lo que sale en cada uno. Dos son ejemplos de
# `eval_idioma.py`, y por eso quedan fuera del test de «otro idioma».
LIMITES = [
    # Un nombre propio con tilde, sin palabras funcionales.
    ("Peña Nieto wins", ESPANOL),
    # Portugués con una palabra que comparte con el español: «para».
    ("Governo anuncia novas medidas para a economia", ESPANOL),
    # «Otro idioma» sólo gana si supera a los dos: «ha» empata con «questo».
    ("Non crederai mai a cosa ha fatto questo cane", ESPANOL),
    # «che» es italiano, y también argentino.
    ("Che Guevara", INDETERMINADO),
]


@pytest.mark.parametrize(
    "titular",
    [
        "You Won't Believe What This Dog Did When His Owner Came Home",
        "Messi's goal in the Champions League",
    ],
)
def test_un_titular_en_ingles_es_ingles(titular):
    assert detectar(titular) == INGLES


@pytest.mark.parametrize(
    "titular",
    [
        "No vas a creer lo que hizo este perro cuando su dueño volvió a casa",
        "Último minuto: dimite el ministro",
        # Sin ninguna palabra de la lista: basta la tilde, o el signo de apertura.
        "Sánchez anuncia elecciones",
        "¿Sabías esto?",
    ],
)
def test_un_titular_en_espanol_es_espanol(titular):
    assert detectar(titular) == ESPANOL


@pytest.mark.parametrize(
    "titular",
    [
        "",
        "   ",
        "2026",
        "!!!",
        "COVID-19",
        "Barcelona 3 Real Madrid 1",
        "Federal Reserve Holds Interest Rates Steady",
        # «un» no está en ninguna lista: en un titular inglés suele ser «UN».
        "Un titular",
    ],
)
def test_sin_ninguna_prueba_es_ingles(titular):
    """El sistema nació para inglés: marcar como extranjero lo que no tiene
    pruebas de nada le quitaría el análisis a quien siempre lo tuvo."""
    assert contar(titular) == {INGLES: 0, ESPANOL: 0, INDETERMINADO: 0}
    assert detectar(titular) == INGLES


@pytest.mark.parametrize(
    ("lengua", "titular"),
    [
        ejemplo
        for ejemplo in EJEMPLOS_DE_OTROS_IDIOMAS
        if ejemplo[1] not in {titular for titular, _ in LIMITES}
    ],
)
def test_otro_idioma_es_indeterminado(lengua, titular):
    assert detectar(titular) == INDETERMINADO, lengua


@pytest.mark.parametrize(("titular", "sale"), LIMITES)
def test_los_limites_del_docstring_siguen_siendo_ciertos(titular, sale):
    """Se equivoca a sabiendas, y lo dice su docstring."""
    assert detectar(titular) == sale


def test_una_letra_de_otro_idioma_sola_no_cuenta():
    """Sin ninguna palabra de sus listas, una «ä» o una «ö» suele ser un nombre
    propio en un titular inglés."""
    titular = "Kimi Räikkönen wins in Monaco"

    assert contar(titular)[INDETERMINADO] == 0
    assert detectar(titular) == INGLES


def test_gana_el_idioma_con_mas_pruebas():
    titular = "The best tapas in Madrid: el secreto de la abuela"

    assert contar(titular) == {INGLES: 2, ESPANOL: 3, INDETERMINADO: 0}
    assert detectar(titular) == ESPANOL


def test_un_empate_entre_ingles_y_espanol_es_ingles():
    """El mismo criterio que sin pruebas: ante la duda, el idioma del sistema."""
    titular = "Real Madrid wins the Copa del Rey"

    assert contar(titular) == {INGLES: 1, ESPANOL: 1, INDETERMINADO: 0}
    assert detectar(titular) == INGLES


def test_cada_idioma_tiene_su_nombre():
    """El motivo que ve quien manda otro idioma lo nombra con `NOMBRES`: un
    idioma sin nombre rompería la frase."""
    assert set(NOMBRES) == set(get_args(Idioma))
