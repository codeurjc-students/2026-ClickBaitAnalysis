"""Entrena el lineal y escribe `nlp/linear_clickbait.json` (#78).

La combinación que eligió `eval_reentreno.py` y que pasó la prueba en `test`:
los rasgos de `linear.rasgos` (palabras, `<number>` y patrones de estructura)
con TF-IDF (`min_df=2`) y una regresión logística, sobre el `train` de
Chakraborty y `train170331` de Webis-17. Los datos los carga el mismo
`cargar_datos` que la comparación, para que lo medido y lo entrenado no puedan
separarse.

El JSON guarda el intercepto y, por rasgo, su peso y su idf, que es todo lo que
la señal necesita para calcular en Python puro. Y una COMPROBACIÓN: unos
titulares de los dos `dev` con la probabilidad que les da sklearn.
`tests/integrations/test_lineal.py` exige que la señal dé la misma; es lo que
vigila que el TF-IDF de `linear.vectorizar` no se separe del de sklearn.

Hasta #78 este guion entrenaba el lineal sobre las pistas del léxico, sólo con
Chakraborty; aquel modelo está congelado en `evaluation/lineal_pistas.py`.

Ejecutar:  python -m backend.evaluation.train_linear
"""

import json

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from backend.evaluation.eval_reentreno import cargar_datos, titulares_y_etiquetas
from backend.integrations.nlp.linear import JSON_FILE, rasgos

# Titulares de cada `dev` que van a la comprobación de paridad.
CASOS_POR_DEV = 10

if __name__ == "__main__":
    datos = cargar_datos()
    titulares, etiquetas = titulares_y_etiquetas(
        datos["chak_train"] + datos["webis_train"]
    )
    vectorizador = TfidfVectorizer(analyzer=rasgos, min_df=2)
    modelo = LogisticRegression(max_iter=1000).fit(
        vectorizador.fit_transform(titulares), etiquetas
    )
    nombres = list(vectorizador.get_feature_names_out())

    casos = [
        titular
        for conjunto in ("chak_dev", "webis_dev")
        for titular, _ in datos[conjunto][:CASOS_POR_DEV]
    ]
    probabilidades = modelo.predict_proba(vectorizador.transform(casos))[:, 1]

    salida = {
        "intercept": float(modelo.intercept_[0]),
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

    print(
        f"{len(titulares)} titulares de entrenamiento · {len(nombres)} rasgos · "
        f"intercepto {salida['intercept']:.4f} -> {JSON_FILE}"
    )
