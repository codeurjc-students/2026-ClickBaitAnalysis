"""El lineal de antes de #78, congelado: una regresión logística sobre las pistas.

Hasta #78, `nlp/linear.py` puntuaba los 390 rasgos del léxico —los cuatro
patrones y las listas de cues— con pesos entrenados sólo en el `train` de
Chakraborty (#72). Desde #78 la señal es otra (las palabras del titular, con
TF-IDF y Webis en el entrenamiento). Este módulo conserva la de antes, con sus
pesos (`lineal_pistas.json`) y el mismo código, para que los guiones que la
midieron —`eval_featurizado` y `eval_acoplamiento` (#109), `eval_umbral_lineal`
(#93)— sigan reproduciendo lo que publicaron, y para que `eval_reentreno`
compare con ella.

Estaba ACOPLADA al léxico por construcción: `featurize_cues` llama a
`lexical.detect`, así que donde el léxico no veía nada, el vector salía vacío
(#109). No es una señal: nada fuera de `evaluation/` lo importa.
"""

import json
import math
from collections import Counter
from functools import cache
from pathlib import Path

from backend.core.models import ToolResult
from backend.integrations.nlp import lexical

JSON_FILE = Path(__file__).resolve().parent / "lineal_pistas.json"
TOP_CUES = 20


@cache
def pesos() -> dict:
    """Pesos, intercepto y nombres de rasgos del modelo de antes de #78."""
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


def predict(headline, top_cues: int = TOP_CUES):
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
            "top_cues": s_contribs[:top_cues],  # Las que más empujaron
            "headline": headline,
        }
    )


def _sigmoid(z: int):
    return 1 / (1 + math.exp(-z))
