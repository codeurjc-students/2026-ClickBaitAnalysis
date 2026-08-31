"""Validación EXTERNA (issue #76): evaluar los detectores en un dataset ajeno.

Los splits de #72 dan honestidad interna (no afinar sobre el test), pero todo
sale de Chakraborty (misma distribución). Este script mide la generalización
real evaluando la vía shipeada (lexical.detect / linear.predict) sobre
Webis-Clickbait-17 (tuits de 27 medios USA, dominio distinto) SIN reentrenar
ni afinar nada: cero adaptación, número honesto de transferencia.

LOS DOS SPLITS (#121)

Webis reparte el corpus en trozos **disjuntos**, como cualquier competición, y
conviene no confundirlos: medido, comparten UN titular de 2.380. El zip del
segundo se llama «train-170630» pero su carpeta interna dice «validation», que es
la nomenclatura del Clickbait Challenge.

- ``train170331`` — 2.459. El extracto original de #76, y el que por defecto
  siguen cargando quienes ya llamaban a ``load_external()``.
- ``validation170630`` — 19.484. Ocho veces más, y trae los CINCO juicios
  individuales de cada anotador (ver ``eval_ambiguedad``).

Ejecutar:  python -m backend.evaluation.eval_external [split]
"""

import gzip
import json
from pathlib import Path

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from backend.integrations.nlp import lexical, linear

_EXTERNAL_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "external"

SPLITS = {
    "train170331": "webis17_train170331.jsonl.gz",
    "validation170630": "webis17_validation170630.jsonl.gz",
}

# Se conserva como defecto el de #76 para que los números ya publicados sigan
# saliendo con la misma llamada: cambiar el defecto reescribiría en silencio el
# significado de todo lo medido antes.
SPLIT_POR_DEFECTO = "train170331"


def _ruta(split: str) -> Path:
    if split not in SPLITS:
        raise ValueError(f"split desconocido «{split}»; hay {sorted(SPLITS)}")
    return _EXTERNAL_DIR / SPLITS[split]


def load_external(split: str = SPLIT_POR_DEFECTO) -> list[tuple[str, int, float]]:
    """Extracto vendorizado -> lista de (headline, label, truthMean)."""
    return [(r["headline"], r["label"], r["truthMean"]) for r in load_records(split)]


def load_records(split: str = SPLIT_POR_DEFECTO) -> list[dict]:
    """Igual, pero sin tirar campos.

    ``load_external`` devuelve ternas por compatibilidad con sus consumidores,
    y en esa forma se pierden el ``id`` y los ``truthJudgments`` — que son
    justamente lo que hace falta para cruzar splits y para medir el techo de la
    tarea. Quien los necesite usa esta.
    """
    with gzip.open(_ruta(split), "rt", encoding="utf-8") as f:
        return [json.loads(linea) for linea in f]


if __name__ == "__main__":
    import sys

    split = sys.argv[1] if len(sys.argv) > 1 else SPLIT_POR_DEFECTO
    print(f"split: {split}")
    data = load_external(split)
    y_true = [label for _, label, _ in data]
    pos = sum(y_true)
    print(
        f"Webis-17 (externo): {len(data)} muestras, {pos} clickbait ({pos / len(data):.1%})"
    )

    y_rules = [
        1 if lexical.detect(h).data["score"] >= lexical.THRESHOLD else 0
        for h, _, _ in data
    ]
    y_linear = [1 if linear.predict(h).data["is_clickbait"] else 0 for h, _, _ in data]

    for name, y_pred in (("reglas", y_rules), ("lineal", y_linear)):
        p, r, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, average="binary", zero_division=0
        )
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        print(
            f"{name}: P={p:.3f}  R={r:.3f}  F1={f1:.3f}   (tp={tp} fp={fp} fn={fn} tn={tn})"
        )
