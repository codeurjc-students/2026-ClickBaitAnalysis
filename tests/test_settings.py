"""La configuración no enseña los secretos (#93).

Un test de #93 falló con un `AttributeError` sobre `settings`, y pytest imprimió
el objeto entero: las tres claves de API, en claro, en la salida. Con
`SecretStr`, su `repr` es '**********' y el valor sólo sale con
`get_secret_value()`, en el punto donde se usa.

Con claves de prueba, nunca las del `.env`: este fichero comprueba que no se
ven, y no puede enseñarlas él si falla.

Y el defecto de `nlp_backend`, que pasó a `local` en #236, y la configuración
del español (#230).
"""

import pytest
from pydantic import ValidationError

from backend.config.settings import ModeloConInvocacion, Settings

CLAVES_DE_PRUEBA = {
    "guardian_api_key": "clave-guardian-de-prueba",
    "nyt_api_key": "clave-nyt-de-prueba",
    "hf_token": "token-hf-de-prueba",
    "gnews_api_key": "clave-gnews-de-prueba",
    "newsdata_api_key": "clave-newsdata-de-prueba",
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


def test_las_claves_de_las_noticias_en_espanol_son_opcionales(monkeypatch):
    """#235: que falte una clave de noticias no puede tumbar el análisis, y un
    despliegue cuyo `.env` no las tenga tiene que seguir arrancando. Sin ellas,
    cada herramienta dice qué falta."""
    monkeypatch.delenv("GNEWS_API_KEY", raising=False)
    monkeypatch.delenv("NEWSDATA_API_KEY", raising=False)
    obligatorias = {
        campo: clave
        for campo, clave in CLAVES_DE_PRUEBA.items()
        if campo not in ("gnews_api_key", "newsdata_api_key")
    }

    configuracion = Settings(**obligatorias, _env_file=None)

    assert configuracion.gnews_api_key is None
    assert configuracion.newsdata_api_key is None


# La configuración del español (#230): la misma forma que la del inglés.


def test_los_modelos_del_espanol_se_leen_del_entorno(monkeypatch):
    monkeypatch.setenv(
        "NLP_MODELS_ES",
        '{"detect_clickbait": {"id": "otro/multilingue",'
        ' "task": "zero-shot-classification"}, "analyze_sentiment": "otro/tono"}',
    )

    modelos = Settings(**CLAVES_DE_PRUEBA, _env_file=None).nlp_models_es

    assert modelos["detect_clickbait"] == ModeloConInvocacion(
        id="otro/multilingue", task="zero-shot-classification"
    )
    assert modelos["analyze_sentiment"] == "otro/tono"


def test_en_espanol_el_modo_tambien_es_solo_de_la_dedicada():
    with pytest.raises(ValidationError):
        Settings(
            nlp_models_es={"analyze_sentiment": {"id": "otro/tono"}},
            **CLAVES_DE_PRUEBA,
        )


def test_en_espanol_solo_se_configura_el_umbral_de_la_incoherencia():
    """El léxico no analiza español: un umbral suyo en español sería un ajuste
    que no hace nada, y así falla al arrancar."""
    configuracion = Settings(
        nlp_thresholds_es={"detect_clickbait_incoherence": 0.25},
        **CLAVES_DE_PRUEBA,
    )
    assert configuracion.nlp_thresholds_es == {"detect_clickbait_incoherence": 0.25}

    with pytest.raises(ValidationError):
        Settings(
            nlp_thresholds_es={"detect_clickbait_lexical": 2},
            **CLAVES_DE_PRUEBA,
        )
