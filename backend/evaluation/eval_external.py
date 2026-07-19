"""Validación EXTERNA (issue #76): evaluar los detectores en un dataset ajeno.

Los splits de #72 dan honestidad interna (no afinar sobre el test), pero todo
sale de Chakraborty (misma distribución). Este script mide la generalización
real evaluando la vía shipeada (lexical.detect / linear.predict) sobre
Webis-Clickbait-17 (tuits de 27 medios USA, dominio distinto) SIN reentrenar
ni afinar nada: cero adaptación, número honesto de transferencia.

Ejecutar:  python -m backend.evaluation.eval_external
"""

import gzip
import json
from pathlib import Path

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from backend.integrations.nlp import lexical, linear

EXTERNAL_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "external"
    / "webis17_train170331.jsonl.gz"
)


def load_external() -> list[tuple[str, int, float]]:
    """Carga el extracto vendorizado -> lista de (headline, label, truthMean)."""
    data = []
    with gzip.open(EXTERNAL_FILE, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            data.append((r["headline"], r["label"], r["truthMean"]))
    return data


if __name__ == "__main__":
    data = load_external()
    y_true = [label for _, label, _ in data]
    pos = sum(y_true)
    print(f"Webis-17 (externo): {len(data)} muestras, {pos} clickbait ({pos/len(data):.1%})")

    y_rules = [
        1 if lexical.detect(h).data["score"] >= lexical.THRESHOLD else 0
        for h, _, _ in data
    ]
    y_linear = [
        1 if linear.predict(h).data["is_clickbait"] else 0 for h, _, _ in data
    ]

    for name, y_pred in (("reglas", y_rules), ("lineal", y_linear)):
        p, r, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, average="binary", zero_division=0
        )
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        print(f"{name}: P={p:.3f}  R={r:.3f}  F1={f1:.3f}   (tp={tp} fp={fp} fn={fn} tn={tn})")
