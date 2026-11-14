"""La regla de la clave de `BaseAPI` (#259).

Las pruebas de cada cliente comprueban su caso; éstas, la regla misma, con dos
clientes de mentira: uno que declara `CLAVE` y otro que no, como el del tiempo
u Ollama. La regla vive en `make_request`, por donde pasa toda petición, para
que ningún método —tampoco uno nuevo— pueda olvidarla.
"""

import pytest
import respx
from httpx import Response
from structlog.testing import capture_logs

from backend.core.base_api import BaseAPI

URL = "https://ejemplo.invalido/"
CLAVE_DE_PRUEBA = "clave-de-prueba-259"


class ConClave(BaseAPI):
    BASE_URL = URL
    CLAVE = "EJEMPLO_API_KEY"


class SinClave(BaseAPI):
    BASE_URL = URL


@pytest.mark.asyncio
async def test_sin_la_clave_que_pide_no_sale_a_la_red():
    with respx.mock(assert_all_called=False) as router:
        ruta = router.get(f"{URL}datos").mock(return_value=Response(200, json={}))
        result = await ConClave().make_request("datos", "get")

    assert not ruta.called
    assert not result.success
    assert "EJEMPLO_API_KEY" in result.error


@pytest.mark.asyncio
async def test_con_la_clave_pide_y_la_manda():
    cliente = ConClave()
    cliente.API_KEY = CLAVE_DE_PRUEBA
    with respx.mock(assert_all_called=False) as router:
        ruta = router.get(f"{URL}datos").mock(return_value=Response(200, json={}))
        result = await cliente.make_request("datos", "get")

    assert result.success
    assert ruta.calls.last.request.url.params["api-key"] == CLAVE_DE_PRUEBA


@pytest.mark.asyncio
async def test_una_api_que_no_pide_clave_pide_sin_ella():
    """El tiempo y Ollama no declaran `CLAVE`: la regla no les cambia nada."""
    with respx.mock(assert_all_called=False) as router:
        ruta = router.get(f"{URL}datos").mock(return_value=Response(200, json={}))
        result = await SinClave().make_request("datos", "get")

    assert ruta.called
    assert result.success


@pytest.mark.asyncio
async def test_un_fallo_imprevisto_deja_su_traza():
    """R10.2 (#292): un 200 que no es JSON no es un error HTTP ni de conexión,
    así que cae en el `except` genérico. Fuera sale la frase pública; al
    registro, hasta #292, sólo el tipo y el mensaje, sin la traza."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{URL}datos").mock(return_value=Response(200, text="no es json"))
        with capture_logs() as registrado:
            result = await SinClave().make_request("datos", "get")

    assert not result.success
    assert "no previsto" in result.error
    fallo = next(linea for linea in registrado if linea["event"] == "api.error")
    assert "Traceback (most recent call last)" in fallo.get("traza", "")
    assert "JSONDecodeError" in fallo.get("traza", "")
