"""Entrena el lineal y escribe `nlp/linear_clickbait.json` (#78, #231).

Desde #231 es BILINGÜE: los rasgos de `linear.rasgos` (palabras, `<number>` y
patrones de estructura) con TF-IDF (`min_df=2`) y una regresión logística, sobre
el `train` de Chakraborty, `train170331` de Webis-17 y el `train` de TA1C. Lo
eligió `eval_lineal_es.py` frente a uno sólo para el español, con la regla
publicada en #231, y pasó la prueba en los tres `test`. Se entrena con las
mismas funciones que lo midieron (`cargar`, `entrenamiento` y `entrenar`), para
que lo medido y lo entrenado no puedan separarse.

El JSON guarda el intercepto, el UMBRAL con el que vota (0,35 desde #231, que
eligió la regla de #78 sobre los tres `dev`) y, por rasgo, su peso y su idf: todo
lo que la señal necesita para calcular en Python puro. Y una COMPROBACIÓN: unos
titulares de los tres `dev` con la probabilidad que les da sklearn.
`tests/integrations/test_lineal.py` exige que la señal dé la misma; es lo que
vigila que el TF-IDF de `linear.vectorizar` no se separe del de sklearn.

Hasta #78 este guion entrenaba el lineal sobre las pistas del léxico, sólo con
Chakraborty; aquel modelo está congelado en `evaluation/lineal_pistas.py`. De
#78 a #231, el mismo de ahora sin TA1C y con el umbral en 0,5.

Ejecutar:  python -m backend.evaluation.train_linear
"""

import json

from backend.evaluation.eval_lineal_es import (
    BILINGUE,
    FEATURIZACION,
    UMBRAL_DE_LA_ELEGIDA,
    cargar,
    entrenamiento,
)
from backend.evaluation.eval_reentreno import entrenar, titulares_y_etiquetas
from backend.integrations.nlp.linear import JSON_FILE

# Titulares de cada `dev` que van a la comprobación de paridad.
CASOS_POR_DEV = 10
DEVS_DE_LA_COMPROBACION = ("chak_dev", "webis_dev", "ta1c_validation")

if __name__ == "__main__":
    datos = cargar()
    pares = entrenamiento(BILINGUE, datos)
    vectorizador, modelo = entrenar(FEATURIZACION, pares)
    nombres = list(vectorizador.get_feature_names_out())

    casos = [
        titular
        for conjunto in DEVS_DE_LA_COMPROBACION
        for titular, _ in datos[conjunto][:CASOS_POR_DEV]
    ]
    probabilidades = modelo.predict_proba(vectorizador.transform(casos))[:, 1]

    salida = {
        "intercept": float(modelo.intercept_[0]),
        "threshold": UMBRAL_DE_LA_ELEGIDA,
        "weights": {
            nombre: float(peso)
            for nombre, peso in zip(nombres, modelo.coef_[0], strict=True)
        },
        "idf": {
            nombre: float(idf)
            for nombre, idf in zip(nombres, vectorizador.idf_, strict=True)
        },
        "comprobacion": [
            {"headline": titular, "probability": float(probabilidad)}
            for titular, probabilidad in zip(casos, probabilidades, strict=True)
        ],
    }
    with open(JSON_FILE, "w", encoding="utf-8") as fichero:
        json.dump(salida, fichero, sort_keys=True, ensure_ascii=False)

    titulares, _ = titulares_y_etiquetas(pares)
    print(
        f"{len(titulares)} titulares de entrenamiento · {len(nombres)} rasgos · "
        f"intercepto {salida['intercept']:.4f} · umbral {salida['threshold']} -> {JSON_FILE}"
    )
