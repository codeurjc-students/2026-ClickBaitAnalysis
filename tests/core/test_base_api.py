"""La regla de la clave de `BaseAPI` (#259).

Las pruebas de cada cliente comprueban su caso; éstas, la regla misma, con dos
clientes de mentira: uno que declara `CLAVE` y otro que no, como el del tiempo
u Ollama. La regla vive en `make_request`, por donde pasa toda petición, para
que ningún método —tampoco uno nuevo— pueda olvidarla.
"""

import pytest
import respx
from httpx import Response

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
