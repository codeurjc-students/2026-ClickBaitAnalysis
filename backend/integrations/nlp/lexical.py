from pathlib import Path
import re, ast

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
    "all_caps": re.compile(r"\b[A-Z]{4,}\b"),
    # 4 mayúsculas seguidas (evitar pillar ALGUNAS siglas) NASA, NATO...
    "ellipsis": re.compile(r"\.\.\.|…"),  # ... o …
}

CATEGORIES = (
    list(WORD_CUES) + list(PHRASE_CUES) + list(PATTERNS)
)  # Usado para featurizar en el modelo linear

# Pistas necesarias para considerarse clickbait.
# Default t=1 (mejor F1≈0.85, P≈R). Modo conservador: t=2 (precisión≈0.97). TODO: Parametrizar

# Creamos un orden para reutilizar en linear_model (igual que CATEGORIES).
# No aplica PATTERNS (no se pueden determinar, son reglas)

# Orden alfabético por defecto.
# Desempaquetamos de set a string
ALL_CUES = sorted(set().union(*WORD_CUES.values(), *PHRASE_CUES.values()))
THRESHOLD = 1


def detect(headline: str) -> ToolResult:

    if not headline or not headline.strip():
        return ToolResult.fail("El titular está vacío o no es válido")

    original = headline
    lowered = headline.lower()
    matches = []
    # Palabras + '. Usar finditter para recibir posiciones

    # Words
    for m in re.finditer(r"[\w']+", lowered):  # Cada palabra
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
    is_clickbait = score >= THRESHOLD
    return ToolResult.ok(
        {
            "score": score,
            "is_clickbait": is_clickbait,
            "matches": matches,
            "headline": headline,
        }
    )
