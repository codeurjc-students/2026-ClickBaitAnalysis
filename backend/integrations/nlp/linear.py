import json
import math
from collections import Counter
from pathlib import Path

from backend.core.models import ToolResult
from backend.integrations.nlp import lexical

JSON_FILE = Path(__file__).resolve().parent / "linear_clickbait.json"

# print(str(JSON_FILE))


with open(JSON_FILE, encoding="utf-8") as f:
    JSON = json.load(f)


def featurize_cues(headline) -> list[int]:  # -> vector
    result = lexical.detect(headline)

    categories_list = []
    cue_list = []
    for match in result.data["matches"]:
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

    vector = featurize_cues(headline)
    contribs = []
    for w, name, x in zip(JSON["weights"], JSON["feature_names"], vector, strict=True):
        if x != 0:
            contr = w * x
            contribs.append((name, contr))

    s_contribs = sorted(
        contribs,
        key=lambda par: par[1],  # Contribuciones mayores
        reverse=True,
    )

    z = sum(contr for _, contr in s_contribs) + JSON["intercept"]  # w * x
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
