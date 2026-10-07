"""El lineal sobre las palabras del titular (#75, #78).

Hasta #78, el lineal puntuaba las pistas del léxico, y la mitad de los
titulares salía con el vector vacío. Desde #78 sus rasgos son las palabras, los
números (como `<number>`) y los patrones de estructura, con TF-IDF, y se
entrena con Chakraborty y Webis-17 (`evaluation/eval_reentreno.py`).

La inferencia es Python puro, sin sklearn, que no está en `requirements.txt`.
El riesgo es que el entrenamiento y la señal dejen de calcular lo mismo sin que
nada falle: lo vigila la paridad con las probabilidades que dio sklearn, que
`train_linear.py` guarda en el propio JSON.
"""

import math

import pytest

from backend.integrations.nlp import linear

DESCONOCIDO = "zzqx qqxz"


def test_los_rasgos_son_las_palabras_los_numeros_y_los_patrones():
    rasgos = linear.rasgos("10 Things You Won't BELIEVE About 2015?")

    # Los números, como rasgo propio: un año dice algo del corpus, no del
    # clickbait de un titular cualquiera.
    assert rasgos.count("<number>") == 2
    assert "10" not in rasgos and "2015" not in rasgos
    assert {"things", "you", "won't", "believe", "about"} <= set(rasgos)
    # Los patrones se miran sobre el titular original: en minúsculas, las
    # mayúsculas desaparecen.
    assert {"<leading_number>", "<question>", "<all_caps>"} <= set(rasgos)


def test_los_rasgos_quitan_las_convenciones_de_tuit():
    """Webis-17 son tuits: `RT`, menciones y enlaces son formato, no titular."""
    assert linear.rasgos("RT @nytimes: Obama wins http://t.co/abc") == [
        "obama",
        "wins",
    ]


def test_vectorizar_da_norma_uno_y_no_cuenta_lo_desconocido():
    vector = linear.vectorizar("You won't believe these 10 things")

    assert math.isclose(math.sqrt(sum(valor**2 for valor in vector.values())), 1.0)
    assert set(vector) <= set(linear.pesos()["weights"])
    assert linear.vectorizar(DESCONOCIDO) == {}


def test_reproduce_las_probabilidades_de_sklearn():
    """La paridad: lo que calcula la señal es lo que se entrenó."""
    comprobacion = linear.pesos()["comprobacion"]

    assert len(comprobacion) >= 10
    for caso in comprobacion:
        probabilidad = linear.predict(caso["headline"]).unwrap()["probability"]
        assert probabilidad == pytest.approx(caso["probability"], abs=1e-9), caso[
            "headline"
        ]


def test_sin_rasgos_conocidos_la_probabilidad_es_la_del_intercepto():
    resultado = linear.predict(DESCONOCIDO).unwrap()

    intercepto = linear.pesos()["intercept"]
    assert resultado["probability"] == pytest.approx(1 / (1 + math.exp(-intercepto)))
    assert resultado["top_cues"] == []


def test_la_explicacion_son_las_contribuciones_ordenadas():
    """Cada pista es un rasgo con su peso × su tf-idf, de más a menos."""
    titular = "10 things you won't believe"
    resultado = linear.predict(titular).unwrap()
    vector = linear.vectorizar(titular)
    pesos = linear.pesos()["weights"]

    contribuciones = [contribucion for _, contribucion in resultado["top_cues"]]
    assert contribuciones == sorted(contribuciones, reverse=True)
    for rasgo, contribucion in resultado["top_cues"]:
        assert contribucion == pytest.approx(pesos[rasgo] * vector[rasgo])
