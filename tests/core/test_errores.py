"""Pruebas de `describir_error`: la regla de #163 y los casos medidos en #164."""

import httpx
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from backend.core.errores import describir_error

URL_CON_SECRETO = "https://ejemplo.invalido/search?api-key=clave-de-prueba-7f3a9c"


def _error_http(codigo: int) -> httpx.HTTPStatusError:
    """Un error HTTP como el de httpx, con la URL —y la clave— en su texto."""
    peticion = httpx.Request("GET", URL_CON_SECRETO)
    respuesta = httpx.Response(codigo, request=peticion)
    return httpx.HTTPStatusError(
        f"Client error for url '{URL_CON_SECRETO}'",
        request=peticion,
        response=respuesta,
    )


def test_un_error_http_da_codigo_y_nombre_sin_la_url():
    motivo = describir_error(_error_http(421))

    assert motivo == "HTTP 421 Misdirected Request"
    assert "clave-de-prueba" not in motivo


def test_otro_error_da_el_nombre_de_su_tipo_y_no_su_texto():
    motivo = describir_error(httpx.ConnectError("All connection attempts failed"))

    assert motivo == "ConnectError"


def test_abre_el_grupo_en_vez_de_describirlo():
    """Lo que enseñaba la pantalla de Sistema era el texto del grupo: «unhandled
    errors in a TaskGroup (1 sub-exception)», sin el motivo real."""
    grupo = ExceptionGroup("unhandled errors in a TaskGroup", [_error_http(421)])

    assert describir_error(grupo) == "HTTP 421 Misdirected Request"


def test_abre_grupos_anidados():
    """Medido: una ruta que no existe llega como un grupo DENTRO de otro."""
    sesion_terminada = McpError(ErrorData(code=-32000, message="Session terminated"))
    grupo = ExceptionGroup("exterior", [ExceptionGroup("interior", [sesion_terminada])])

    assert describir_error(grupo) == "McpError"


def test_un_timeout_llega_sin_grupo():
    """Medido: un servidor que acepta la conexión y no contesta da un
    `TimeoutError` suelto, no envuelto."""
    assert describir_error(TimeoutError()) == "TimeoutError"


def test_varios_errores_juntan_sus_motivos_sin_repetir_y_en_orden():
    grupo = ExceptionGroup(
        "varios",
        [httpx.ConnectError("uno"), TimeoutError(), httpx.ConnectError("dos")],
    )

    assert describir_error(grupo) == "ConnectError, TimeoutError"
