"""La configuración no enseña los secretos (#93).

Un test de #93 falló con un `AttributeError` sobre `settings`, y pytest imprimió
el objeto entero: las tres claves de API, en claro, en la salida. Con
`SecretStr`, su `repr` es '**********' y el valor sólo sale con
`get_secret_value()`, en el punto donde se usa.

Con claves de prueba, nunca las del `.env`: este fichero comprueba que no se
ven, y no puede enseñarlas él si falla.
"""

import pytest

from backend.config.settings import Settings

CLAVES_DE_PRUEBA = {
    "guardian_api_key": "clave-guardian-de-prueba",
    "nyt_api_key": "clave-nyt-de-prueba",
    "hf_token": "token-hf-de-prueba",
}


@pytest.mark.parametrize("presentar", [repr, str])
def test_la_configuracion_no_enseña_las_claves(presentar):
    """`repr` es lo que imprime pytest al fallar sobre el objeto, y `str` lo que
    sale de un log o un `print` descuidado."""
    texto = presentar(Settings(**CLAVES_DE_PRUEBA))

    for clave in CLAVES_DE_PRUEBA.values():
        assert clave not in texto


def test_el_valor_sigue_disponible_donde_se_usa():
    configuracion = Settings(**CLAVES_DE_PRUEBA)

    for campo, clave in CLAVES_DE_PRUEBA.items():
        assert getattr(configuracion, campo).get_secret_value() == clave
