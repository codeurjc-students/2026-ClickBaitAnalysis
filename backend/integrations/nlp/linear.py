"""Señal interpretable: una regresión logística sobre las pistas del léxico.

Inferencia en Python puro —`sigmoid(w·x + b)`, sin sklearn ni torch— con los
pesos de `linear_clickbait.json`, que entrena y serializa
`evaluation/train_linear.py` sobre el split de entrenamiento de Chakraborty
(#72). Devuelve la probabilidad de clickbait y los cues que más la empujaron,
que son su explicación (R3.8).

Está ACOPLADA al léxico por construcción: `featurize_cues` llama a
`lexical.detect`, así que donde el léxico no ve nada, el vector sale vacío
(#109; lo cuenta la ficha).
"""

import json
import math
from collections import Counter
from functools import cache
from pathlib import Path

from backend.core.models import ToolResult
from backend.integrations.nlp import lexical

JSON_FILE = Path(__file__).resolve().parent / "linear_clickbait.json"


# Los pesos se leen en el PRIMER USO, no al importar (#108). Leerlos a nivel de
# módulo hacía que importar la señal —aunque fuera para inspeccionarla— abriera
# y parseara el fichero, y fallara si no estaba. Es el patrón de `local.py` y
# `incoherence.py` con sus modelos; aquí basta una lectura cacheada.
@cache
def pesos() -> dict:
    """Pesos, intercepto y nombres de rasgos del modelo, tal como los serializó
    `evaluation/train_linear.py`."""
    with open(JSON_FILE, encoding="utf-8") as fichero:
        return json.load(fichero)


def featurize_cues(headline) -> list[int]:  # -> vector
    result = lexical.detect(headline)

    categories_list = []
    cue_list = []
    for match in result.unwrap()["matches"]:
        if match["category"] in lexical.PATTERNS:
            categories_list.append(match["category"])
        else:
            cue_list.append(match["cue"])

    contador_category = Counter(categories_list)
    contador_cue = Counter(cue_list)
    vector = [contador_category[cat] for cat in lexical.PATTERNS] + [
        contador_cue[cue] for cue in lexical.ALL_CUES
    ]
    return vector


def predict(headline):

    if not headline or not headline.strip():
        return ToolResult.fail("El titular está vacío o no es válido")

    modelo = pesos()
    vector = featurize_cues(headline)
    contribs = []
    for w, name, x in zip(
        modelo["weights"], modelo["feature_names"], vector, strict=True
    ):
        if x != 0:
            contr = w * x
            contribs.append((name, contr))

    s_contribs = sorted(
        contribs,
        key=lambda par: par[1],  # Contribuciones mayores
        reverse=True,
    )

    z = sum(contr for _, contr in s_contribs) + modelo["intercept"]  # w * x
    p = _sigmoid(z)
    is_clickbait = p >= 0.5
    return ToolResult.ok(
        {
            "is_clickbait": is_clickbait,
            "probability": p,
            "top_cues": s_contribs[:20],  # Top 20 pesos (TODO: Configurable)
            "headline": headline,
        }
    )


def _sigmoid(z: int):
    return 1 / (1 + math.exp(-z))
