"""Tras #78 (2026-10-07) - ¿Qué acercaría el lineal al techo humano en tuits?

Con #78 el lineal da F1 0,534 en `webis_test`, lejos del 0,665 de una persona
contra el consenso de las demás (#121) y del dedicado. Dos preguntas, medidas
en los dos `dev` y nunca en `test`:

1. `curva`: ¿más tuits en el entrenamiento? F3 con Chakraborty más N tuits de
   Webis-17: primero los de `train170331` (lo que usa el lineal) y después los
   de `webis_test`, COMO ENTRENAMIENTO. De `webis_test` no se mide nada, así que
   no se abre como examen; pero un lineal que los usara necesitaría otro reparto
   con su propio `test`. Se repite también sin Chakraborty, y cada submuestra
   con tres semillas.
2. `bigramas`: ¿pares de palabras consecutivas («you won't», «here's why»)? F3
   frente a F3 con bigramas, con los datos de ahora y con todos los tuits; con el
   intervalo bootstrap de la diferencia en `webis_dev` y los bigramas que más
   pesan, que son los que vería quien lea la tarjeta.

Exploratorio: no cambia la señal. Ejecutar desde la raíz:

    .venv/bin/python spikes/lineal_curva.py [curva] [bigramas]
"""

import random
import statistics
import sys
import time
from itertools import pairwise
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.evaluation.eval_reentreno import (  # noqa: E402
    cargar_datos,
    diferencia_con_intervalo,
    entrenar,
    predecir,
    titulares_y_etiquetas,
)
from backend.evaluation.splits import load_split  # noqa: E402
from backend.integrations.nlp import lexical, linear  # noqa: E402

F3 = "F3 tf-idf normalizado"
SEMILLAS = (24, 25, 26)
# Un número dentro de la secuencia de palabras, antes de pasarlo a `<number>`;
# `lexical.TOKEN` lo reconoce como palabra y no choca con ninguna real.
_HUECO_NUMERO = "zznumerozz"

DATOS = cargar_datos()
CHAK_TRAIN = DATOS["chak_train"]
WEBIS_TRAIN = DATOS["webis_train"]
EXTRA = load_split("webis_test")
EVALUACIONES = {
    "webis_dev": titulares_y_etiquetas(DATOS["webis_dev"]),
    "chak_dev": titulares_y_etiquetas(DATOS["chak_dev"]),
}


def secuencia(titular: str) -> list[str]:
    """Las palabras del titular EN ORDEN, normalizadas como en `linear.rasgos`."""
    limpio = linear.RETUIT.sub(
        " ", linear.MENCION.sub(" ", linear.ENLACE.sub(" ", titular))
    )
    palabras = lexical.TOKEN.findall(
        linear.NUMERO.sub(f" {_HUECO_NUMERO} ", limpio).lower()
    )
    return ["<number>" if palabra == _HUECO_NUMERO else palabra for palabra in palabras]


def rasgos_con_bigramas(titular: str) -> list[str]:
    """Los rasgos de F3 más cada par de palabras consecutivas."""
    palabras = secuencia(titular)
    pares = [f"{primera} {segunda}" for primera, segunda in pairwise(palabras)]
    return linear.rasgos(titular) + pares


def entrenar_con_bigramas(pares: list[tuple[str, int]]):
    titulares, etiquetas = titulares_y_etiquetas(pares)
    vectorizador = TfidfVectorizer(analyzer=rasgos_con_bigramas, min_df=2)
    matriz = vectorizador.fit_transform(titulares)
    return vectorizador, LogisticRegression(max_iter=1000).fit(matriz, etiquetas)


def predicciones(vectorizador, modelo) -> dict[str, list[int]]:
    return {
        nombre: predecir(vectorizador, modelo, titulares)[0]
        for nombre, (titulares, _) in EVALUACIONES.items()
    }


def f1_por_dev(prediccion: dict[str, list[int]]) -> dict[str, float]:
    return {
        nombre: f1_score(etiquetas, prediccion[nombre])
        for nombre, (_, etiquetas) in EVALUACIONES.items()
    }


def tuits(cuantos: int, semilla: int) -> list[tuple[str, int]]:
    """`cuantos` tuits: de `train170331` primero, y después de `webis_test`."""
    azar = random.Random(semilla)
    if cuantos <= len(WEBIS_TRAIN):
        return azar.sample(WEBIS_TRAIN, cuantos)
    return WEBIS_TRAIN + azar.sample(EXTRA, cuantos - len(WEBIS_TRAIN))


def _resumen(medidas: list[dict[str, float]], clave: str) -> str:
    valores = [medida[clave] for medida in medidas]
    media = statistics.mean(valores)
    if len(valores) == 1:
        return f"{media:.3f}       "
    return f"{media:.3f} ±{(max(valores) - min(valores)) / 2:.3f}"


def _fila_de_la_curva(cuantos: int) -> None:
    completos = (0, len(WEBIS_TRAIN), len(WEBIS_TRAIN) + len(EXTRA))
    semillas = SEMILLAS[:1] if cuantos in completos else SEMILLAS
    con_chak, sin_chak = [], []
    for semilla in semillas:
        muestra = tuits(cuantos, semilla)
        con_chak.append(f1_por_dev(predicciones(*entrenar(F3, CHAK_TRAIN + muestra))))
        if cuantos:
            sin_chak.append(f1_por_dev(predicciones(*entrenar(F3, muestra))))
    sin_texto = (
        f"{_resumen(sin_chak, 'webis_dev')}   {_resumen(sin_chak, 'chak_dev')}"
        if sin_chak
        else "—"
    )
    print(
        f"  {cuantos:>6}   {_resumen(con_chak, 'webis_dev')}   "
        f"{_resumen(con_chak, 'chak_dev')}   |   {sin_texto}",
        flush=True,
    )


def curva() -> None:
    print("\n== curva: F1 en los dos dev según los tuits de entrenamiento (± = medio rango de 3 semillas)")
    print("    tuits   CON Chakraborty: webis_dev   chak_dev   |   SIN Chakraborty: webis_dev   chak_dev")
    print("  -- train170331")
    for fraccion in (0, 0.25, 0.5, 0.75, 1):
        _fila_de_la_curva(round(fraccion * len(WEBIS_TRAIN)))
    print("  -- más tuits de webis_test, como entrenamiento")
    for anadidos in (2500, 5000, 10000, len(EXTRA)):
        _fila_de_la_curva(len(WEBIS_TRAIN) + anadidos)


def bigramas() -> None:
    print("\n== bigramas: F3 frente a F3 con pares de palabras consecutivas")
    _, etiquetas_webis = EVALUACIONES["webis_dev"]
    for nombre, pares in (
        ("Chakraborty + train170331 (lo de ahora)", CHAK_TRAIN + WEBIS_TRAIN),
        ("Chakraborty + todos los tuits", CHAK_TRAIN + WEBIS_TRAIN + EXTRA),
    ):
        print(f"  -- {nombre}")
        vectorizador_f3, modelo_f3 = entrenar(F3, pares)
        vectorizador_bi, modelo_bi = entrenar_con_bigramas(pares)
        prediccion_f3 = predicciones(vectorizador_f3, modelo_f3)
        prediccion_bi = predicciones(vectorizador_bi, modelo_bi)
        for etiqueta, vectorizador, prediccion in (
            ("F3", vectorizador_f3, prediccion_f3),
            ("F3 + bigramas", vectorizador_bi, prediccion_bi),
        ):
            medidas = f1_por_dev(prediccion)
            print(
                f"     {etiqueta:14} rasgos {len(vectorizador.get_feature_names_out()):>6} · "
                f"F1 webis_dev {medidas['webis_dev']:.3f} · F1 chak_dev {medidas['chak_dev']:.3f}"
            )
        diferencia, bajo, alto = diferencia_con_intervalo(
            etiquetas_webis, prediccion_bi["webis_dev"], prediccion_f3["webis_dev"]
        )
        print(
            f"     F1 webis_dev (con bigramas − sin): {diferencia:+.4f}, "
            f"intervalo del 95 % [{bajo:+.4f}, {alto:+.4f}]"
        )
        nombres = vectorizador_bi.get_feature_names_out()
        de_bigramas = sorted(
            (
                (peso, rasgo)
                for rasgo, peso in zip(nombres, modelo_bi.coef_[0], strict=True)
                if " " in rasgo
            ),
            reverse=True,
        )
        print("     bigramas a favor:", ", ".join(f"{rasgo} {peso:.2f}" for peso, rasgo in de_bigramas[:10]))
        print("     bigramas en contra:", ", ".join(f"{rasgo} {peso:.2f}" for peso, rasgo in de_bigramas[-10:]))


PARTES = {"curva": curva, "bigramas": bigramas}

if __name__ == "__main__":
    elegidas = sys.argv[1:] or list(PARTES)
    desconocidas = [parte for parte in elegidas if parte not in PARTES]
    if desconocidas:
        sys.exit(f"Partes desconocidas: {desconocidas}. Hay: {list(PARTES)}")
    inicio = time.perf_counter()
    print(
        f"Chakraborty train {len(CHAK_TRAIN)} · train170331 {len(WEBIS_TRAIN)} · "
        f"webis_test como entrenamiento {len(EXTRA)} · webis_dev "
        f"{len(EVALUACIONES['webis_dev'][0])} · chak_dev {len(EVALUACIONES['chak_dev'][0])}"
    )
    for parte in elegidas:
        PARTES[parte]()
    print(f"\n{time.perf_counter() - inicio:.0f} s")
