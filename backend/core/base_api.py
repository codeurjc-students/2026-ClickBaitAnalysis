import asyncio

from aiolimiter import AsyncLimiter
import httpx

from backend.core.models import ToolResult
import structlog

log = structlog.get_logger()


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

    # Daily limiting
    DAILY_LIMIT: int | None = None  # Aplicamos polimorfismo de nuevo

    def __init__(self):
        self._limiter = AsyncLimiter(self.RATE_CALLS, self.RATE_PERIOD)
        # formato (max llamadas en X secs)
        self._call_count = 0
        self._remaining: int | None = None

    # Metodo polimórfico: Guardian usa x-ratelimit. Nyt es desconocido (dejamos none), cada api aplica por su cuenta.
    def _read_quota(self, response: httpx.Response) -> None:
        if self.DAILY_LIMIT is not None:
            self._remaining = self.DAILY_LIMIT - self._call_count

    # Vars de lectura

    @property
    def remaining_quota(self) -> int | None:
        return self._remaining

    @property
    def call_count(self) -> int:
        return self._call_count

    # Mejor atributo privado con método público para asegurarnos de que SOLO ES DE LECTURA (getter).
    # La otra clase no nota la diferencia ya que con @property se puede nombrar como si fuera atrbuto público.

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
                        self._call_count += 1
                        # Tambien registra reintentos por si acaso
                        if method.upper() == "GET":
                            response = await client.get(
                                url,
                                headers=headers,
                                params=params,
                                timeout=self.TIMEOUT,
                            )

                        elif method.upper() == "POST":
                            response = await client.post(
                                url,
                                headers=headers,
                                params=params,
                                timeout=self.TIMEOUT,
                                json=json,
                            )
                        else:
                            return ToolResult.fail(f"Unsupported HTTP method: {method}")
                        response.raise_for_status()
                        self._read_quota(response)  # Tras llamada exitosa
                        log.info(
                            "api.call",
                            api=type(self).__name__,  # Nombre de la API que lo llama
                            endpoint=endpoint,
                            call_count=self._call_count,
                            remaining_quota=self._remaining,  # None si la API no declara límite
                        )
                        return ToolResult.ok(response.json())

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
