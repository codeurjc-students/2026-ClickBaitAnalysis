"""El contrato común de los backends NLP: `NLPBackend`.

Dos implementaciones de la misma interfaz, que elige `nlp_backend` en
`factory.py`: `remote.py`, la Inference API de Hugging Face, y `local.py`,
`transformers` en el propio proceso. Las señales llaman a `classify` o a
`zero_shot` sin saber dónde corre el modelo.
"""

from abc import ABC, abstractmethod

from backend.core.models import ToolResult


class NLPBackend(ABC):
    """Contrato común de los backends NLP (remoto HF / local transformers).

    Ambos métodos DEBEN devolver ToolResult.ok({"label": ..., "score": ...}).
    """

    @abstractmethod
    async def classify(self, text: str, model: str) -> ToolResult:
        """Clasificación de texto (p.ej. sentiment)."""

    @abstractmethod
    async def zero_shot(self, text: str, model: str, labels: list[str]) -> ToolResult:
        """Clasificación zero-shot (p.ej. clickbait con bart-mnli)."""
