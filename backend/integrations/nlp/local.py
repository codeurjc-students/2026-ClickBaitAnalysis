from backend.core.models import ToolResult
from backend.integrations.nlp.base import NLPBackend

import asyncio


class LocalNLPClient(NLPBackend):

    # Evitamos cargar en cada llamada añadiendo permanencia
    def __init__(self) -> None:

        self._pipelines: dict[tuple[str, str], object] = {}

    # Para devolver

    def _get_pipeline(self, task: str, model: str) -> object:
        key = (task, model)
        if key not in self._pipelines:
            from transformers import pipeline

            pipe = pipeline(task, model=model)
            self._pipelines[key] = pipe

        return self._pipelines[key]

    # Usamos tupla con la clave (modelo, task), para evitar que se usen modelos para tasks no especificadas

    # Tasks que nos interesan "text-classification" y "zero-shot-classification"

    async def classify(self, text: str, model: str) -> ToolResult:
        try:
            pipe = self._get_pipeline("text-classification", model)
            result = await asyncio.to_thread(
                pipe, text
            )  # Usamos thread ya que es una accion bloqueante
            # (func, *args)

            # El modelo termina

            return ToolResult.ok(result[0])
        except Exception as e:
            return ToolResult.fail(f"Error inesperado usando el modelo {model}: {e}")

    async def zero_shot(self, text: str, model: str, labels: list[str]) -> ToolResult:
        try:
            pipe = self._get_pipeline("zero-shot-classification", model)
            output = await asyncio.to_thread(
                pipe, text, candidate_labels=labels
            )  # candidate_labels NO es posicional, tiene que declararse
            result = {"label": output["labels"][0], "score": output["scores"][0]}
            return ToolResult.ok(result)  # Etiqueta, valor (ganadores)
        except Exception as e:
            return ToolResult.fail(f"Error inesperado usando el modelo {model}: {e}")
