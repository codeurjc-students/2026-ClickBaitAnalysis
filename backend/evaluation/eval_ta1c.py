"""¿Cuánto acertaba el sistema en español, tratándolo como inglés? (issue #229)

Hasta #229 un titular en español se analizaba como cualquier otro: las listas
del léxico son inglesas, el lineal y los modelos se entrenaron en inglés, y nada
avisaba. Este guion mide qué daba eso en TA1C, el corpus de clickbait en español
etiquetado por personas, para que la memoria tenga la cifra de partida.

Pasa cada teaser por las mismas señales y la misma agregación que `/analyze`
(`_run_signals`, `_aggregate` y `_overall` del orquestador), con el cuerpo del
artículo para la incoherencia, y compara con la etiqueta humana:

- cada señal: P, R y F1, y en cuántos teasers respondió;
- el léxico: en cuántos no encontró ninguna pista;
- el veredicto: «es clickbait» (`deceptive` o `stylistic_clickbait`, como en
  `eval_veredicto`) frente a la etiqueta, y el reparto de los veredictos.

Desde #230 la puerta del idioma vive en `_run_signals`, así que este guion le
pasa `INGLES` como idioma del titular y del cuerpo, a propósito: mide lo que
midió el punto de partida de #229, el español tratado como inglés, pero con las
señales de hoy. Sus cifras exactas (veredicto 0,038) eran las del sistema de
entonces: desde #231 el lineal es bilingüe y las mayúsculas con tilde cuentan.

Con `--como-produccion` (#231) le pasa en cambio el idioma que detecta
`core.idioma`, como hace `analyze()`: es el sistema de verdad sobre el
español, con las señales que lo analizan —desde #231, el lineal— y las demás
en `not_applicable`. Cada señal que gane el español (#232, #233) cambia esta
cifra, y no la de arriba.

Sobre `validation` (700), no sobre `test`, que queda para elegir los modelos del
español (#231–#233). Por eso estas cifras NO se comparan tal cual con las
publicadas en TA1C (TF-IDF + XGBoost 0,61 y BETO afinado 0,84), que son de su
`test`.

    NLP_BACKEND=local .venv/bin/python -m backend.evaluation.eval_ta1c
    NLP_BACKEND=local .venv/bin/python -m backend.evaluation.eval_ta1c --como-produccion
"""

import asyncio
import gzip
import json
import sys
import time
from collections import Counter

from sklearn.metrics import precision_recall_fscore_support

from backend.analysis.domain import OverallVerdict, SignalStatus
from backend.analysis.orchestrator import _aggregate, _overall, _run_signals
from backend.core.idioma import INGLES, detectar
from backend.evaluation.ta1c_extract import DESTINO_CUERPOS, DESTINO_TEASERS

PARTE = "validation"
POSITIVOS = {OverallVerdict.DECEPTIVE, OverallVerdict.STYLISTIC_CLICKBAIT}


def cargar(parte: str = PARTE) -> list[dict]:
    """Los teasers de una parte, con el cuerpo de su artículo cruzado por id."""
    with gzip.open(DESTINO_CUERPOS, "rt", encoding="utf-8") as fichero:
        cuerpos = {
            registro["id"]: registro["cuerpo"] for registro in map(json.loads, fichero)
        }
    with gzip.open(DESTINO_TEASERS, "rt", encoding="utf-8") as fichero:
        return [
            {**registro, "cuerpo": cuerpos.get(registro["id"], "")}
            for registro in map(json.loads, fichero)
            if registro["parte"] == parte
        ]


async def evaluar(filas: list[dict], como_produccion: bool) -> list[dict]:
    """El voto de cada señal y el veredicto de cada teaser, como en `/analyze`."""
    resultados = []
    inicio = time.perf_counter()
    for indice, fila in enumerate(filas, start=1):
        cuerpo = fila["cuerpo"] or None
        if como_produccion:
            # Como `analyze()`: los idiomas que detecta `core.idioma`.
            idioma = detectar(fila["headline"])
            idioma_del_cuerpo = detectar(cuerpo) if cuerpo else None
        else:
            # `INGLES` en los dos, a propósito: ver el docstring.
            idioma, idioma_del_cuerpo = INGLES, (INGLES if cuerpo else None)
        senales = await _run_signals(
            fila["headline"], cuerpo, idioma, idioma_del_cuerpo
        )
        resultados.append(
            {
                "senales": {
                    senal.name: {
                        "estado": senal.status,
                        "voto": senal.is_clickbait,
                        "datos": senal.data,
                    }
                    for senal in senales
                },
                "veredicto": _overall(_aggregate(senales)),
            }
        )
        if indice % 100 == 0:
            print(
                f"  {indice}/{len(filas)} · {time.perf_counter() - inicio:.0f} s",
                flush=True,
            )
    return resultados


def _prf(etiquetas: list[int], predichas: list[int]) -> str:
    precision, recall, f1, _ = precision_recall_fscore_support(
        etiquetas, predichas, average="binary", zero_division=0
    )
    return f"P {precision:.3f} · R {recall:.3f} · F1 {f1:.3f}"


def informe(filas: list[dict], resultados: list[dict], como_produccion: bool) -> None:
    etiquetas = [fila["label"] for fila in filas]
    clickbait = sum(etiquetas)
    modo = (
        "con el idioma detectado, como producción"
        if como_produccion
        else "con el español tratado como inglés"
    )
    print(
        f"\n== TA1C {PARTE}, {modo}: {len(filas)} teasers, {clickbait} clickbait ({clickbait / len(filas):.1%})"
    )

    print("\n== cada señal, frente a la etiqueta humana")
    for nombre in resultados[0]["senales"]:
        votan = [
            (etiqueta, resultado["senales"][nombre]["voto"])
            for etiqueta, resultado in zip(etiquetas, resultados, strict=True)
            if resultado["senales"][nombre]["estado"] == SignalStatus.OK
            and resultado["senales"][nombre]["voto"] is not None
        ]
        estados = Counter(
            resultado["senales"][nombre]["estado"].value for resultado in resultados
        )
        if not votan:
            print(f"  {nombre:30} no vota · {dict(estados)}")
            continue
        print(
            f"  {nombre:30} {_prf([etiqueta for etiqueta, _ in votan], [int(voto) for _, voto in votan])}"
            f" · vota en {len(votan)} · {dict(estados)}"
        )

    # Sólo donde se ejecutó: con el idioma detectado, el léxico no analiza el
    # español, y contar sus «cero pistas» sobre los 700 diría que siempre las
    # encuentra.
    lexicos = [
        resultado["senales"]["detect_clickbait_lexical"]["datos"] or {}
        for resultado in resultados
        if resultado["senales"]["detect_clickbait_lexical"]["estado"] == SignalStatus.OK
    ]
    if lexicos:
        sin_pistas = sum(1 for datos in lexicos if datos.get("score") == 0)
        print(
            f"\n  el léxico no encuentra ninguna pista en {sin_pistas} de {len(lexicos)} ({sin_pistas / len(lexicos):.1%})"
        )
    else:
        print("\n  el léxico no se ejecutó en ningún teaser")

    veredictos = [resultado["veredicto"] for resultado in resultados]
    print("\n== el veredicto")
    print(
        f"  «es clickbait» frente a la etiqueta: {_prf(etiquetas, [int(veredicto in POSITIVOS) for veredicto in veredictos])}"
    )
    reparto = Counter(veredicto.value for veredicto in veredictos)
    print(
        "  reparto: "
        + " · ".join(
            f"{nombre} {cuantos} ({cuantos / len(filas):.1%})"
            for nombre, cuantos in reparto.most_common()
        )
    )
    print(
        "\n  (Las cifras publicadas de TA1C —TF-IDF + XGBoost 0,61, BETO 0,84— son de su "
        "`test`, no de `validation`: no se comparan tal cual.)"
    )


def main() -> None:
    filas = cargar()
    print(
        f"== {len(filas)} teasers de TA1C {PARTE}; {sum(1 for fila in filas if not fila['cuerpo'].strip())} sin cuerpo"
    )
    como_produccion = "--como-produccion" in sys.argv
    resultados = asyncio.run(evaluar(filas, como_produccion))
    informe(filas, resultados, como_produccion)


if __name__ == "__main__":
    main()
