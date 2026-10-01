"""Backend NLP remoto: la Inference API de Hugging Face (`HFClient`).

Implementa `NLPBackend` sobre `BaseAPI`, con tres reintentos ante un timeout o
un 503 (E4-02). Es, con `factory.py`, **el único módulo de la capa NLP que lee
`settings`**, porque necesita el token. Se llamaba `client.py` hasta #108, que
lo renombró para que el par `remote.py` / `local.py` diga lo que es: dos
implementaciones de la misma interfaz.

Ojo: `hf-inference` NO sirve ningún modelo de clickbait. El dedicado responde
`400 Model not supported by provider`, y es permanente, así que en despliegue
va `nlp_backend=local` (#156).

Una respuesta con forma inesperada se registra entera y NO se publica: hasta el
2026-09-24 el mensaje de fallo llevaba la respuesta cruda del proveedor, y salía
por `/analyze`, por `/tools/.../execute` y por MCP. Era una quinta puerta de #89,
que se escapó al tapar las cuatro de entonces.
"""

import structlog

from backend.config.settings import settings
from backend.core.base_api import BaseAPI
from backend.core.errores import mensaje_publico
from backend.core.models import ToolResult
from backend.integrations.nlp.base import NLPBackend

log = structlog.get_logger()


def _fallo(tarea: str, model: str, error: Exception, respuesta: object) -> ToolResult:
    """Registra la respuesta que no se esperaba y devuelve lo que puede salir.

    La frase pública es la misma que da `local.py` para lo mismo, así que quien
    lee la tarjeta de una señal caída ve lo mismo sea cual sea el backend. La
    respuesta va al log recortada, como hace `base_api.py` con los cuerpos de
    error: sirve para diagnosticar y no tiene por qué caber entera.
    """
    log.warning(
        "nlp.remoto.fallo",
        tarea=tarea,
        modelo=model,
        tipo=type(error).__name__,
        detalle=str(error),
        respuesta=str(respuesta)[:1000],
    )
    return ToolResult.fail(f"El modelo `{model}` {mensaje_publico(error)}.")


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
        except (IndexError, KeyError, TypeError, ValueError) as error:
            return _fallo("text-classification", model, error, result.data)

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
        except (IndexError, KeyError, TypeError, ValueError) as error:
            return _fallo("zero-shot-classification", model, error, result.data)
