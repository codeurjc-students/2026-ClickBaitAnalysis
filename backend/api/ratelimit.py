"""Limitación de velocidad de las peticiones ENTRANTES (R12.4, #169).

**No confundir con el limitador de `core/base_api.py`.** Aquél acota las
llamadas que este sistema HACE a Guardian y a NYT, y su remedio es esperar:
nadie sale perjudicado, sólo se va más despacio. Esto acota lo que el sistema
RECIBE, y el remedio es rechazar — el que espera es el cliente.

**Por qué aquí y no en Caddy.** El módulo `caddy-ratelimit` obligaría a
construir la imagen de Caddy con `xcaddy` en vez de usar la oficial, y sobre
todo no se podría probar en el CI: el criterio de #169 pide una prueba que lo
fije. Aquí se prueba con el `TestClient` que ya existe, y el presupuesto puede
depender de la ruta, que es lo que hace falta — no cuesta lo mismo `/analyze`,
que ocupa la CPU durante segundos, que `GET /history`, que lee SQLite.

**Ventana deslizante, no cubo de fichas.** Guardando las marcas de tiempo de
las peticiones recientes, el `Retry-After` sale exacto —cuándo cae la más
vieja— y el límite se explica solo: «diez en cualquier minuto». Un cubo de
fichas gasta menos memoria, pero su respuesta a «¿cuánto espero?» es una
aproximación y su comportamiento en ráfaga cuesta más de contar.

**El estado vive en memoria del proceso**, que vale porque el backend está
atado a UN SOLO worker desde #125: cada proceso carga sus propios modelos. Con
varios workers los contadores divergirían y el límite efectivo sería el
declarado multiplicado por el número de procesos.
"""

import math
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from backend.config.settings import settings

log = structlog.get_logger()

# Los tres grupos, por lo que cuesta atender una petición.
CARAS = "caras"
SONDEO = "sondeo"
RESTO = "resto"

# El 429 para el contrato. Se DECLARA, no sólo se lanza: si no sale en el
# OpenAPI, el cliente Angular que se genera de él no sabe que ese código existe,
# y quien escribe la pantalla lo descubre leyendo este fichero.
#
# Se aplica UNA vez, en el constructor de `FastAPI`, y no ruta por ruta: el
# límite es de la aplicación entera y no hay ninguna exenta, así que declararlo
# seis veces sólo abría la puerta a que la séptima se olvidara.
RESPUESTA_429: dict[int | str, dict[str, str]] = {
    429: {
        "description": (
            "Se superó el límite de peticiones. La cabecera `Retry-After` dice "
            "cuántos segundos esperar."
        )
    }
}


@dataclass(frozen=True)
class Presupuesto:
    """Cuántas peticiones caben en cuánto tiempo."""

    peticiones: int
    ventana_s: float


class Limitador:
    """Lleva la cuenta por (cliente, grupo) y dice si cabe una petición más.

    El reloj se INYECTA para que las pruebas puedan adelantar el tiempo en vez
    de dormir: una suite que duerme un minuto para comprobar que la ventana se
    vacía deja de ejecutarse en cada cambio, que es como no tenerla.
    """

    def __init__(
        self,
        presupuestos: Mapping[str, Presupuesto],
        reloj: Callable[[], float] = time.monotonic,
        podar_desde: int = 1000,
    ) -> None:
        self._presupuestos = dict(presupuestos)
        self._reloj = reloj
        self._podar_desde = podar_desde
        self._marcas: dict[tuple[str, str], deque[float]] = {}

    @property
    def seguidos(self) -> int:
        """Cuántos pares (cliente, grupo) se están vigilando ahora mismo.

        Es lo que la poda tiene que mantener acotado, y lo único que se puede
        mirar desde fuera para comprobar que lo hace.
        """
        return len(self._marcas)

    def consumir(self, cliente: str, grupo: str) -> float | None:
        """Anota la petición y devuelve `None`; o los segundos que faltan.

        Devolver `None` cuando pasa y un número cuando no, en vez de un par
        `(bool, float)`, deja el caso normal en una sola comprobación para quien
        llama — y el número sólo existe cuando significa algo.
        """
        presupuesto = self._presupuestos[grupo]
        ahora = self._reloj()
        marcas = self._marcas.setdefault((cliente, grupo), deque())

        caducan_antes_de = ahora - presupuesto.ventana_s
        while marcas and marcas[0] <= caducan_antes_de:
            marcas.popleft()

        if len(marcas) >= presupuesto.peticiones:
            return marcas[0] + presupuesto.ventana_s - ahora

        marcas.append(ahora)
        self._podar(ahora)
        return None

    def _podar(self, ahora: float) -> None:
        """Olvida a los clientes que ya no tienen ninguna marca viva.

        Sin esto el diccionario crece con cada IP que pase por delante, y una
        aplicación expuesta a internet ve muchas. Sólo se recorre cuando hay
        bastantes claves, así que el coste queda amortizado.
        """
        if len(self._marcas) < self._podar_desde:
            return

        olvidables = [
            clave
            for clave, marcas in self._marcas.items()
            if not marcas
            or marcas[-1] <= ahora - self._presupuestos[clave[1]].ventana_s
        ]
        for clave in olvidables:
            del self._marcas[clave]


def presupuestos_vigentes() -> dict[str, Presupuesto]:
    """Los presupuestos que dice la configuración AHORA.

    Se leen al construir el limitador y no al importar el módulo, por lo mismo
    que la factoría de #119: una constante de módulo aquí sería un ajuste que no
    hace nada, y no falla — engaña.
    """
    ventana = settings.rate_limit_window_s
    return {
        CARAS: Presupuesto(settings.rate_limit_analyze, ventana),
        SONDEO: Presupuesto(settings.rate_limit_health, ventana),
        RESTO: Presupuesto(settings.rate_limit_default, ventana),
    }


_limitador: Limitador | None = None


def obtener_limitador() -> Limitador:
    """El limitador del proceso, construido en el primer uso."""
    global _limitador
    if _limitador is None:
        _limitador = Limitador(presupuestos_vigentes())
    return _limitador


def reiniciar_limitador() -> None:
    """Olvida los contadores y los presupuestos.

    La usan las pruebas: sin esto, lo que consume un test se lo encuentra el
    siguiente, y un presupuesto cambiado con `monkeypatch` no tendría efecto
    porque el limitador ya estaría construido con el anterior.
    """
    global _limitador
    _limitador = None


def sin_prefijo_de_montaje(ruta: str, raiz: str) -> str:
    """La ruta como la declara la aplicación, sin el prefijo donde está montada.

    Hace falta porque **un middleware corre antes del enrutado**, y ahí la ruta
    todavía puede traer el prefijo de montaje. Caddy quita `/api` con
    `handle_path`, pero uvicorn arranca con `--root-path /api` y —medido en la
    máquina 1 con uvicorn 0.41.0— **lo devuelve al `scope`**: la aplicación
    recibe `path="/api/health"` con `root_path="/api"`. Starlette se lo quita
    después, al enrutar; aquí todavía no.

    Es la regla del enrutado de Starlette, escrita a mano para no depender de
    una función privada suya, y con un tornillo más apretado: el prefijo se
    quita sólo si termina donde acaba un segmento. Un `startswith` pelado
    convertiría `/apidocumentos` en `documentos` con la raíz en `/api`.
    """
    if raiz and (ruta == raiz or ruta.startswith(raiz + "/")):
        return ruta[len(raiz) :] or "/"
    return ruta


def grupo_de(metodo: str, ruta: str) -> str | None:
    """A qué presupuesto pertenece una petición; `None` si está exenta.

    **`OPTIONS` queda exento**, y no es un detalle menor: es la comprobación
    previa de CORS, la hace el navegador solo y no cuesta nada. Si gastara
    presupuesto, un 429 ahí no llegaría a la pantalla como un límite —el
    navegador lo traduce a un fallo de CORS— y la interfaz diría que no hay API
    al otro lado, que es justo el diagnóstico equivocado.

    La ruta se compara con la que declara la aplicación, así que quien llame
    tiene que haberle quitado antes el prefijo de montaje: ver
    `sin_prefijo_de_montaje`.
    """
    if metodo == "OPTIONS":
        return None

    # `POST /chat` también es cara: cada conversación ocupa la GPU compartida
    # hasta un minuto (#189). Sondearla (`GET /chat/{id}`) sólo lee memoria.
    ejecucion_de_herramienta = ruta.startswith("/tools/") and ruta.endswith("/execute")
    if metodo == "POST" and (ruta in ("/analyze", "/chat") or ejecucion_de_herramienta):
        return CARAS

    if ruta == "/health":
        return SONDEO

    return RESTO


async def limitar_peticiones(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware: cuenta la petición y la rechaza con 429 si pasa del cupo.

    El cliente es `request.client.host`. Detrás de Caddy eso sería la IP del
    PROXY —y un límite por proxy castigaría a todos a la vez—, así que uvicorn
    arranca con `--forwarded-allow-ips` y Caddy sobrescribe `X-Forwarded-For`
    con la dirección real. Lo que sostiene que esa cabecera sea creíble es que
    la API no se publica: si algún día se publicara su puerto, falsificarla
    volvería a ser trivial. Lo vigila `tests/test_compose.py`.
    """
    if not settings.rate_limit_enabled:
        return await call_next(request)

    ruta = sin_prefijo_de_montaje(request.url.path, request.scope.get("root_path", ""))
    grupo = grupo_de(request.method, ruta)
    if grupo is None:
        return await call_next(request)

    cliente = request.client.host if request.client else "desconocido"
    espera = obtener_limitador().consumir(cliente, grupo)
    if espera is None:
        return await call_next(request)

    # Al alza y nunca menos de 1: un `Retry-After: 0` invita a reintentar de
    # inmediato, que es justo lo que se acaba de rechazar.
    segundos = max(1, math.ceil(espera))
    log.warning(
        "api.limite",
        cliente=cliente,
        grupo=grupo,
        metodo=request.method,
        ruta=ruta,
        espera_s=segundos,
    )
    return JSONResponse(
        status_code=429,
        content={
            "detail": f"Demasiadas peticiones. Vuelve a intentarlo en {segundos} s."
        },
        headers={"Retry-After": str(segundos)},
    )
