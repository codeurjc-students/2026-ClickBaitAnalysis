import asyncio
from backend.core.models import ToolResult


class IncoherenceDetector:
    MODEL = "all-MiniLM-L6-v2"
    THRESHOLD = 0.3  # Lower es clickbait

    def __init__(self) -> None:
        self._model = None  # Singleton

    def _get_model(
        self,
    ):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL)
        return self._model

    async def detect(self, headline: str, content: str) -> ToolResult:
        try:
            model = self._get_model()
            embeding = await asyncio.to_thread(model.encode, [headline, content])

            # Usa coseno por debajo
            sim = model.similarity(embeding[0], embeding[1]).item()
            inc = sim < self.THRESHOLD
            return ToolResult.ok(
                {
                    "similarity": sim,
                    "incoherent": inc,
                    "headline": headline,
                    "content": content,
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Error inesperado calculando incoherencia: {e}")
