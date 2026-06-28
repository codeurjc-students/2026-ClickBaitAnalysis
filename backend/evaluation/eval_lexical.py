import gzip  # Descompresión en memoria (wow)
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_fscore_support,
)  # Import conjunto
from backend.integrations.nlp import lexical

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"  # Carpeta data


def _load_file(path, label) -> list:
    results = []
    with gzip.open(path, "rt", encoding="utf-8") as f:  # Read text mode
        for line in f:
            headline = line.strip()  # Quita /n
            if headline:  # ya es "" para las blancas → falsy → fuera
                results.append((headline, label))
    return results


def load_dataset() -> list:
    clickbait_path = DATA_DIR / "clickbait_data.gz"
    non_clickbait_path = DATA_DIR / "non_clickbait_data.gz"
    data = _load_file(clickbait_path, 1)  # Asignamos 1 a clickbait
    data += _load_file(non_clickbait_path, 0)

    return data


def score_headlines(data) -> list:
    score_list = []
    for headline, label in data:
        result = lexical.detect(headline)
        if result.success:
            score_list.append((result.data["score"], label))
    return score_list


def confusion(scored, threshold):
    y_true, y_pred = _pred_getter(scored, threshold)

    # Obtener la matriz
    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1])

    # Extraer los 4 cuadrantes
    tn, fp, fn, tp = matrix.ravel()  # ORDEN IMPORTANTE

    return tn, fp, fn, tp


def metrics(scored, threshold):
    y_true, y_pred = _pred_getter(scored, threshold)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    return precision, recall, f1


def _pred_getter(scored, threshold):
    y_true = []
    y_pred = []
    for score, label in scored:
        pred = 1 if score >= threshold else 0
        y_true.append(label)
        y_pred.append(pred)

    return y_true, y_pred


def sweep(scored):
    max_score = max(s for s, _ in scored)  # hasta dónde barrer
    results = []
    for t in range(1, max_score + 1):
        # De threshold 1 al Max de score que ha salido (0 todo permite, no sirve)
        precision, recall, f1 = metrics(scored, t)
        results.append((t, precision, recall, f1))
    return results
