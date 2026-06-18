import asyncio
from backend.core.models import ToolResult


class IncoherenceDetector:
    MODEL = "all-MiniLM-L6-v2"
    THRESHOLD = 0.3  # Lower es clickbait

    def __init__(self) -> None:
        self._model = None  # Singleton

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL)
        return self._model

    async def detect(self, headline: str, content: str) -> ToolResult:
        try:
            model = self._get_model()
            embedding = await asyncio.to_thread(model.encode, [headline, content])

            # Usa coseno por debajo
            sim = model.similarity(embedding[0], embedding[1]).item()
            # Devuelve tensors, necesitamos .item

            # Tensors: Array de Números de N dimensiones. En este caso 2 embeddings x 1-D Tensor de 384 floats de los cuales reducimos a 1 float x 1 Tensor con similarity (y que extraemos con item)

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
