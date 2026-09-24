"""La base de los clientes HTTP de las integraciones: `BaseAPI`.

Cada cliente (Guardian, NYT, el tiempo, Hugging Face) hereda de aquí y declara
sólo lo suyo como atributos de clase: URL, autenticación y límites. Lo común lo
pone `make_request`: el límite de peticiones de cada instancia (`aiolimiter`),
los reintentos —sólo ante un timeout o un 503, y sólo si `MAX_RETRIES` los
pide: Guardian y NYT no reintentan—, la cuenta de llamadas y la cuota restante.

Devuelve siempre un `ToolResult`: un fallo viaja como valor, no como excepción.
Sus mensajes de error SON públicos —salen por `/analyze`, por
`/tools/.../execute` y por las tools MCP—, así que dicen qué pasó con las
palabras de `core/errores.py`, y el detalle (el cuerpo del proveedor, el texto
de la excepción) va al log (#89).
"""

import asyncio

import httpx
import structlog
from aiolimiter import AsyncLimiter

from backend.core.errores import describir_error, mensaje_publico
from backend.core.models import ToolResult

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

                # Los tres mensajes de abajo SE PUBLICAN: salen por `/analyze`,
                # por `/tools/.../execute` y por las tools MCP. Así que dicen qué
                # pasó y nada de cómo está hecho esto por dentro (#89), y el
                # detalle —el cuerpo del proveedor, el texto de la excepción—
                # se registra aquí, que es donde sirve para diagnosticar.
                except httpx.TimeoutException as error:
                    if attempt < self.MAX_RETRIES:
                        await asyncio.sleep(self.RETRY_BACKOFF)
                        continue
                    log.warning(
                        "api.timeout",
                        api=type(self).__name__,
                        endpoint=endpoint,
                        detalle=str(error),
                    )
                    return ToolResult.fail(
                        f"La llamada a la API externa {mensaje_publico(error)}."
                    )
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 503 and attempt < self.MAX_RETRIES:
                        await asyncio.sleep(self.RETRY_BACKOFF)
                        continue
                    log.warning(
                        "api.error_http",
                        api=type(self).__name__,
                        endpoint=endpoint,
                        status=e.response.status_code,
                        cuerpo=e.response.text[:1000],
                    )
                    return ToolResult.fail(
                        f"La API externa respondió {describir_error(e)}."
                    )
                except Exception as error:
                    log.warning(
                        "api.error",
                        api=type(self).__name__,
                        endpoint=endpoint,
                        tipo=type(error).__name__,
                        detalle=str(error),
                    )
                    return ToolResult.fail(
                        f"La llamada a la API externa {mensaje_publico(error)}."
                    )

        # El bucle siempre devuelve: en el último intento los tres manejadores
        # retornan en vez de hacer `continue`. Salvo que `MAX_RETRIES` fuera
        # negativo y `range()` saliera vacío — entonces esto caía por el final
        # devolviendo `None`, y quien llamara haría `.success` sobre él.
        #
        # No es defensa paranoica: la firma promete un `ToolResult` y sin esto la
        # promesa era falsa por un camino, aunque hoy nadie lo recorra. Lo
        # detectó pyright en #139.
        return ToolResult.fail(
            f"No se intentó la llamada: MAX_RETRIES es {self.MAX_RETRIES}."
        )

    # Luego reescribirmos en otra clase que herede de Base API y tenemos POLIMORFISMO!

    def _apply_auth(self, headers: dict, params: dict) -> None:
        if self.API_KEY:
            params[self.API_KEY_PARAM] = self.API_KEY
