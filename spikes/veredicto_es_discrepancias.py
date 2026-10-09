"""#242 (2026-10-09) - Cuando la dedicada y el lineal discrepan en español, ¿quién acierta?

Con la dedicada en español (BETO afinado con TA1C), la forma tiene dos votos en
español: el suyo y el del lineal. `eval_ta1c --como-produccion` da en TA1C
`validation` un veredicto con F1 0,665 (P 0,938, R 0,515), por debajo de la
dedicada sola (0,803): cuando los dos votos discrepan, la forma queda dividida y
el veredicto es `ambiguous`, que no cuenta como clickbait. Eso es la regla de
siempre —una dimensión dividida se enseña, no se resuelve a favor de una
señal—, y este guion mide qué hay dentro de cada veredicto:

- en `ambiguous`, cuántos son clickbait según las personas, y en cada sentido de
  la discrepancia (la dedicada dice sí y el lineal no, o al revés), quién acierta;
- en `factual` y en `stylistic_clickbait`, cuántos son clickbait.

Repite el camino de producción de `eval_ta1c` (`cargar` y `evaluar`, con el
idioma detectado): `eval_ta1c` no guarda los resultados de cada tuit. Unos 70 s
en la GTX, y carga `ggcastle/beto-clickbait-es` del Hub o de la caché.

Ejecutar desde la raíz:

    NLP_BACKEND=local PYTHONPATH=. .venv/bin/python spikes/veredicto_es_discrepancias.py
"""

import asyncio
from collections import Counter

from backend.analysis.domain import SignalStatus
from backend.evaluation.eval_ta1c import cargar, evaluar

DEDICADA = "detect_clickbait"
LINEAL = "detect_clickbait_linear"


def voto(resultado: dict, senal: str) -> bool | None:
    datos = resultado["senales"][senal]
    return datos["voto"] if datos["estado"] == SignalStatus.OK else None


def main() -> None:
    filas = cargar()
    resultados = asyncio.run(evaluar(filas, como_produccion=True))
    etiquetas = [fila["label"] for fila in filas]

    por_veredicto: dict[str, list[tuple[int, dict]]] = {}
    for etiqueta, resultado in zip(etiquetas, resultados, strict=True):
        por_veredicto.setdefault(resultado["veredicto"].value, []).append(
            (etiqueta, resultado)
        )

    print(f"\n== TA1C validation, como producción: {len(filas)} tuits")
    for veredicto, casos in sorted(por_veredicto.items(), key=lambda par: -len(par[1])):
        clickbait = sum(etiqueta for etiqueta, _ in casos)
        print(
            f"  {veredicto:20} {len(casos):4} tuits, {clickbait} clickbait según las personas "
            f"({clickbait / len(casos):.1%})"
        )

    print("\n== dentro de `ambiguous`, por el sentido de la discrepancia")
    sentidos = Counter()
    aciertos = Counter()
    for etiqueta, resultado in por_veredicto.get("ambiguous", []):
        dedicada, lineal = voto(resultado, DEDICADA), voto(resultado, LINEAL)
        if dedicada is None or lineal is None or dedicada == lineal:
            sentido = "otro (no discrepan la dedicada y el lineal)"
            acierta = None
        elif dedicada:
            sentido = "la dedicada dice sí, el lineal no"
            acierta = "la dedicada" if etiqueta == 1 else "el lineal"
        else:
            sentido = "el lineal dice sí, la dedicada no"
            acierta = "el lineal" if etiqueta == 1 else "la dedicada"
        sentidos[sentido] += 1
        if acierta:
            aciertos[(sentido, acierta)] += 1
    for sentido, cuantos in sentidos.most_common():
        detalle = " · ".join(
            f"acierta {quien} en {aciertos[(sentido, quien)]}"
            for quien in ("la dedicada", "el lineal")
            if (sentido, quien) in aciertos
        )
        print(f"  {sentido:46} {cuantos:4}" + (f" · {detalle}" if detalle else ""))


if __name__ == "__main__":
    main()
