from backend.config.settings import settings
from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult


class HFClient(BaseAPI):
    BASE_URL = "https://router.huggingface.co/hf-inference/models/"
    API_KEY = settings.hf_token

    def _apply_auth(self, headers, params):
        headers["Authorization"] = f"Bearer {self.API_KEY}"

    async def classify(self, text: str, model: str) -> ToolResult:
        result = await self.make_request(
            endpoint=model, method="POST", json={"inputs": text}
        )

        if not result.success:
            return result
        try:
            return ToolResult.ok(result.data[0][0])
        except (IndexError, KeyError, TypeError):
            return ToolResult.fail(f"Respuesta inesperada de HF: {result.data}")

    async def zero_shot(self, text: str, model: str, labels: list[str]) -> ToolResult:
        # Método creado para satisfacer nueva lógica de zero-shots y poder correr NLP con llamadas API.
        result = await self.make_request(
            endpoint=model,
            method="POST",
            json={
                "inputs": text,
                "parameters": {"candidate_labels": labels},
            },  # Parametros añadidos para zero shots (necesita labels parseadas para clasificaciones)
        )

        if not result.success:
            return result
        try:
            return ToolResult.ok(result.data[0])
        except (IndexError, KeyError, TypeError):
            return ToolResult.fail(f"Respuesta inesperada de HF: {result.data}")
