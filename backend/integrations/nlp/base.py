# Esta clase abstracta sirve como base para las distintas manera de implementar el NLP  (En otro caso, BaseAPI si llama a sus propios métodos para hacer peticiones)


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
