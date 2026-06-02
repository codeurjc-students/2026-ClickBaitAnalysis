from backend.config.settings import settings
from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult


class HFClient(BaseAPI):
    BASE_URL = "https://router.huggingface.co/hf-inference/models/"
    API_KEY = settings.hf_token

    def _apply_auth(self, headers, params):
        headers["Authorization"] = f"Bearer {self.API_KEY}"

    async def classify(self, text: str, model: str) -> ToolResult:
        return await self.make_request(
            endpoint=model, method="POST", json={"inputs": text}
        )
