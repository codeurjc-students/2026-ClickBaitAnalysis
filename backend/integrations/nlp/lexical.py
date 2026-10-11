"""Señal interpretable: las pistas léxicas y estructurales del clickbait.

Busca en el titular cues de hipérbole y de referencia vaga —listas de
Chakraborty, en `cues/`—, frases gancho y patrones de estructura (número
inicial, interrogación final, mayúsculas, elipsis), y devuelve cada coincidencia
con su posición. La evidencia ES la explicación: no hay ningún modelo detrás.

`THRESHOLD = 1` —una pista basta— es el de mejor F1 (E4-03); con `2` es el modo
conservador, de precisión ≈0,97. Es el defecto: desde #93 el umbral se
configura (`nlp_thresholds`), lo RECIBE `detect` de la factoría y viaja con el
resultado. Los tokens son de dos letras o más desde #69, para que la «I» de
«A.I.» no cuente.
"""

import ast
import re
from pathlib import Path

from backend.core.models import ToolResult

CUES_DIR = Path(__file__).resolve().parent / "cues"


def _load_literal(path):
    with open(path, encoding="utf-8") as f:
        return set(ast.literal_eval(f.read()))
        # Read (string) -> Literal_eval (lista) -> set O(1)
        # NUNCA USAR EVAL, ES CAPAZ DE EJECUTAR COMANDOS!


def _load_lines(path):
    with open(path, encoding="utf-8") as f:
        return {line.strip().lower() for line in f if line.strip()}  # set de str


WORD_CUES = {
    "hyperbole": _load_lines(CUES_DIR / "hyperbolic"),
    "forward_reference": _load_literal(CUES_DIR / "subjects"),
}
PHRASE_CUES = {
    "curiosity_gap": {"what happened next", "doesn't want you to see"},
}
PATTERNS = {
    "leading_number": re.compile(r"^\s*\d+"),
    # Números iniciales (tras espacios en blanco)
    "question": re.compile(r"\?\s*$"),
    # Interrogacion (no entre comillas para excluir citas) Solo pilla comilla cierre
    "all_caps": re.compile(r"\b[A-ZÁÉÍÓÚÜÑ]{4,}\b"),
    # 4 mayúsculas seguidas (evitar pillar ALGUNAS siglas) NASA, NATO... Con
    # las del español desde #231: con `[A-Z]` a secas, la letra con tilde
    # cortaba la palabra, y «ÚLTIMA» o «ESPAÑA» no contaban.
    "ellipsis": re.compile(r"\.\.\.|…"),  # ... o …
}

# Una palabra: dos letras o más, con apóstrofo (desde #69, para que la «I» de
# «A.I.» no cuente). La usa también el lineal desde #78 (`linear.rasgos`), para
# que las dos señales partan el titular igual.
TOKEN = re.compile(r"[\w']{2,}")

# Orden fijo de los cues, que era el de los rasgos del modelo lineal hasta #78:
# lo usa `evaluation/lineal_pistas.py`, que conserva aquel modelo.
# No aplica PATTERNS (no se pueden determinar, son reglas)

# Orden alfabético por defecto.
# Desempaquetamos de set a string
ALL_CUES = sorted(set().union(*WORD_CUES.values(), *PHRASE_CUES.values()))

# Pistas necesarias para considerarse clickbait.
# Default t=1 (mejor F1≈0.85, P≈R). Modo conservador: t=2 (precisión≈0.97).
# Es el DEFECTO (#93): el que decide lo pasa la factoría desde la configuración,
# y los guiones de `evaluation/` miden con éste.
THRESHOLD = 1


def detect(headline: str, threshold: float = THRESHOLD) -> ToolResult:

    if not headline or not headline.strip():
        return ToolResult.fail("El titular está vacío o no es válido")

    original = headline
    lowered = headline.lower()
    matches = []
    # Palabras + '. Usar finditter para recibir posiciones

    # Words

    # Fix: eliminado "i" de cues (En siglas pilla como clickbait)
    for m in TOKEN.finditer(lowered):  # Cada palabra (de 2 letras o más)
        token = m.group()  # Token (string)
        for category, words in WORD_CUES.items():
            # Ej: Hyperbole, amazing
            if token in words:
                matches.append(
                    {
                        "category": category,
                        "cue": token,  # Palabra que encontró
                        "span": list(m.span()),
                        # Posicion Tupla[Inicio, fin] convertida a lista por comodidad, básicamente
                    }
                )

    # Phrases

    for category, phrases in PHRASE_CUES.items():
        for phrase in phrases:  # Cada frase
            for m in re.finditer(re.escape(phrase), lowered):
                # Escapamos para incluir puntuaciones y otros signos
                matches.append(
                    {
                        "category": category,
                        "cue": phrase,  # Frase que encontró
                        "span": list(m.span()),
                    }
                )

    # Estructures:

    for category, pattern in PATTERNS.items():  # Categoría + patrón regex
        for m in pattern.finditer(original):
            matches.append(
                {"category": category, "cue": m.group(), "span": list(m.span())}
            )

    # Recuento final:
    score = len(matches)
    is_clickbait = score >= threshold
    return ToolResult.ok(
        {
            "score": score,
            "is_clickbait": is_clickbait,
            # El umbral VIAJA con el resultado, como el de la incoherencia
            # (#133): la tarjeta lo lee en vez de copiar la regla (#116), que
            # con un umbral configurable dejaría de ser cierta.
            "threshold": threshold,
            "matches": matches,
            "headline": headline,
        }
    )
