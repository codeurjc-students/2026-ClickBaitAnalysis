"""Backend NLP remoto: la Inference API de Hugging Face (`HFClient`).

Implementa `NLPBackend` sobre `BaseAPI`, con tres reintentos ante un timeout o
un 503 (E4-02). Es, con `factory.py`, **el único módulo de la capa NLP que lee
`settings`**, porque necesita el token. Se llamaba `client.py` hasta #108, que
lo renombró para que el par `remote.py` / `local.py` diga lo que es: dos
implementaciones de la misma interfaz.

Ojo: `hf-inference` NO sirve ningún modelo de clickbait. El dedicado responde
`400 Model not supported by provider`, y es permanente, así que en despliegue
va `nlp_backend=local` (#156).
"""

from backend.config.settings import settings
from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult
from backend.integrations.nlp.base import NLPBackend


class HFClient(BaseAPI, NLPBackend):
    # Importante
    BASE_URL = "https://router.huggingface.co/hf-inference/models/"
    API_KEY = settings.hf_token
    MAX_RETRIES = 3

    def _apply_auth(self, headers, params):
        headers["Authorization"] = f"Bearer {self.API_KEY}"

    async def classify(self, text: str, model: str) -> ToolResult:
        result = await self.make_request(
            endpoint=model, method="POST", json={"inputs": text}
        )

        if not result.success:
            return result
        try:
            return ToolResult.ok(result.unwrap()[0][0])
        # `ValueError` lo aporta `unwrap()`: un éxito sin datos es otra forma de
        # respuesta inesperada, y se informa igual que las demás en vez de subir.
        except (IndexError, KeyError, TypeError, ValueError):
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
            return ToolResult.ok(result.unwrap()[0])
        except (IndexError, KeyError, TypeError, ValueError):
            return ToolResult.fail(f"Respuesta inesperada de HF: {result.data}")
