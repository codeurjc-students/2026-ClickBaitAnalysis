import asyncio

from aiolimiter import AsyncLimiter
import httpx

from backend.core.models import ToolResult


class BaseAPI:
    BASE_URL: str = ""
    API_KEY: str | None = None
    TIMEOUT: float = 30.0
    API_KEY_PARAM: str = "api-key"

    # Variables para reintento
    MAX_RETRIES: int = 0  # Guardian/NYT NO reintentan
    RETRY_BACKOFF: float = 1.0  # segundos

    # Rate limiting
    RATE_CALLS: int = 5
    RATE_PERIOD: float = 1.0

    def __init__(self):
        self._limiter = AsyncLimiter(self.RATE_CALLS, self.RATE_PERIOD)
        # formato (max llamadas en X secs)

    async def make_request(
        self,
        endpoint: str,
        method: str,
        params: dict | None = None,
        json: dict | None = None,  # Para llamadas HF
    ) -> ToolResult:
        """Make a request to the  API with proper error handling."""

        headers = {"Accept": "application/json"}

        params = params or {}
        self._apply_auth(headers, params)

        url = f"{self.BASE_URL}{endpoint}"

        async with httpx.AsyncClient() as client:
            for attempt in range(self.MAX_RETRIES + 1):
                try:
                    async with self._limiter:
                        if method.upper() == "GET":
                            response = await client.get(
                                url,
                                headers=headers,
                                params=params,
                                timeout=self.TIMEOUT,
                            )
                            response.raise_for_status()
                            return ToolResult.ok(response.json())
                        elif method.upper() == "POST":
                            response = await client.post(
                                url,
                                headers=headers,
                                params=params,
                                timeout=self.TIMEOUT,
                                json=json,
                            )
                            response.raise_for_status()
                            return ToolResult.ok(response.json())
                        return ToolResult.fail(f"Unsupported HTTP method: {method}")
                except httpx.TimeoutException:
                    if attempt < self.MAX_RETRIES:
                        await asyncio.sleep(self.RETRY_BACKOFF)
                        continue
                    return ToolResult.fail("Request timed out.")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 503 and attempt < self.MAX_RETRIES:
                        await asyncio.sleep(self.RETRY_BACKOFF)
                        continue
                    return ToolResult.fail(
                        f"HTTP error: {e.response.status_code} - {e.response.text}"
                    )
                except Exception as e:
                    return ToolResult.fail(f"An error occurred: {str(e)}")

    # Luego reescribirmos en otra clase que herede de Base API y tenemos POLIMORFISMO!

    def _apply_auth(self, headers: dict, params: dict) -> None:
        if self.API_KEY:
            params[self.API_KEY_PARAM] = self.API_KEY
