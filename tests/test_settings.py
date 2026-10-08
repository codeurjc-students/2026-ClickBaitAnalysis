"""La configuración no enseña los secretos (#93).

Un test de #93 falló con un `AttributeError` sobre `settings`, y pytest imprimió
el objeto entero: las tres claves de API, en claro, en la salida. Con
`SecretStr`, su `repr` es '**********' y el valor sólo sale con
`get_secret_value()`, en el punto donde se usa.

Con claves de prueba, nunca las del `.env`: este fichero comprueba que no se
ven, y no puede enseñarlas él si falla.

Y el defecto de `nlp_backend`, que pasó a `local` en #236.
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


def test_por_defecto_los_modelos_corren_en_local(monkeypatch):
    """Hasta #236 el defecto era `remote`, y la vía remota ya no sirve sin pagar:
    Hugging Face retiró el crédito gratuito el 7 oct 2026, y responde 402 en el
    tono y en el zero-shot (y 400 en la dedicada desde septiembre). En local, lo
    que falla en una instalación sin `torch` dice qué paquete falta (#158).

    Sin `.env` ni variable de entorno: se mide el defecto, no la configuración
    de quien ejecuta los tests."""
    monkeypatch.delenv("NLP_BACKEND", raising=False)

    configuracion = Settings(**CLAVES_DE_PRUEBA, _env_file=None)

    assert configuracion.nlp_backend == "local"
