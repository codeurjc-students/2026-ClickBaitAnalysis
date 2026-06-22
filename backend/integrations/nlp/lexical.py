import re

from backend.core.models import ToolResult

WORD_CUES = {
    "hyperbole": {"amazing", "astonishing"},
    "forward_reference": {"this", "that", "things", "reasons", "ways"},
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

# Pistas necesarias para considerarse clickbait. TODO: Parametrizar
THRESHOLD = 2


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
