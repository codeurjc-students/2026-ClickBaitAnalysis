"""#256 (2026-11-08) - El léxico y la dedicada en `webis_dev`, de la caché del veredicto.

La tabla de resultados en desarrollo de la memoria daba el lineal en `webis_dev`,
y el léxico y la dedicada sobre los 19.484 tuits de `validation170630`, porque se
midieron antes de partirlo (#78). `eval_veredicto` guarda el voto de cada señal
por tuit, así que basta con quedarse con los `id` de `webis_dev`.

No carga ningún modelo y no abre `webis_test`: lo que no está en `webis_dev` se
descarta antes de calcular nada. La caché vive en `var/`, sin versionar, y la
genera `eval_veredicto`. El lineal hace de control, porque su F1 en esta partición
ya está publicado (#231): si no sale 0,535, la caché es de otro sistema y el guion
se para. Se cuentan los que votaron, como en `eval_veredicto.comprobar`.

Ejecutar desde la raíz: .venv/bin/python spikes/senales_webis_dev.py

Resultados (2026-11-08, con la caché del 8 oct):

| Señal | Votan | P | R | F1 |
|---|---|---|---|---|
| Lineal bilingüe, 0,35 (control) | 3.894 | 0,410 | 0,770 | 0,535 |
| Léxico | 3.891 | 0,345 | 0,660 | 0,453 |
| Dedicada | 3.891 | 0,713 | 0,820 | 0,763 |

No votan, por la puerta del idioma (`not_applicable`), 2 tuits en el lineal y 5 en
las otras dos.
"""

import json
from collections import Counter
from pathlib import Path

from sklearn.metrics import precision_recall_fscore_support

RAIZ = Path(__file__).resolve().parent.parent
PARTE = RAIZ / "data" / "splits" / "webis_dev.jsonl"
CACHE = RAIZ / "var" / "veredicto_validation170630.json"

TAMANO = 3_896
CLICKBAIT = 943
CONTROL_LINEAL = 0.535

SENALES = {
    "Lineal bilingüe, 0,35 (control)": "detect_clickbait_linear",
    "Léxico": "detect_clickbait_lexical",
    "Dedicada": "detect_clickbait",
}


def filas_de_dev() -> list[dict]:
    """Las filas de la caché de `webis_dev`, comprobadas contra su partición."""
    with open(PARTE, encoding="utf-8") as fichero:
        etiquetas = {fila["id"]: fila["label"] for fila in map(json.loads, fichero)}
    if len(etiquetas) != TAMANO or sum(etiquetas.values()) != CLICKBAIT:
        raise SystemExit("webis_dev no es el que cita el README")

    filas = [
        fila
        for fila in json.loads(CACHE.read_text(encoding="utf-8"))["filas"]
        if fila["id"] in etiquetas
    ]
    if {fila["id"] for fila in filas} != set(etiquetas):
        raise SystemExit("faltan tuits de webis_dev en la caché")
    if any(fila["label"] != etiquetas[fila["id"]] for fila in filas):
        raise SystemExit("una etiqueta de la caché no coincide con la partición")
    if any(fila.get("rechazado") for fila in filas):
        raise SystemExit("un tuit de webis_dev fue rechazado: la cuenta no sería ésta")
    return filas


def medir(filas: list[dict], senal: str) -> dict:
    """Precisión, recall y F1 de los que votaron."""
    votaron = [fila for fila in filas if fila["senales"][senal]["voto"] is not None]
    precision, recall, f1, _ = precision_recall_fscore_support(
        [fila["label"] for fila in votaron],
        [int(fila["senales"][senal]["voto"]) for fila in votaron],
        average="binary",
        zero_division=0,
    )
    return {
        "votan": len(votaron),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "estados": dict(Counter(fila["senales"][senal]["estado"] for fila in filas)),
    }


def main() -> None:
    filas = filas_de_dev()
    resultados = {nombre: medir(filas, senal) for nombre, senal in SENALES.items()}
    control = resultados["Lineal bilingüe, 0,35 (control)"]["f1"]
    if round(control, 3) != CONTROL_LINEAL:
        raise SystemExit(f"control: el lineal da {control:.4f}, y no {CONTROL_LINEAL}")

    print(f"webis_dev en la caché: {len(filas)} tuits")
    print("| Señal | Votan | P | R | F1 | Estados |")
    print("|---|---|---|---|---|---|")
    for nombre, medida in resultados.items():
        print(
            f"| {nombre} | {medida['votan']} | {medida['precision']:.3f} | "
            f"{medida['recall']:.3f} | {medida['f1']:.3f} | {medida['estados']} |"
        )


if __name__ == "__main__":
    main()
