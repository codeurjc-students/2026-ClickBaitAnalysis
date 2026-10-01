"""`TextoOpcional`: la ausencia escrita como texto es ausencia (#197).

El modelo del agente llamó a `analyze_headline` con `content="None"` —la cadena,
no la ausencia—, la herramienta lo tomó como el cuerpo de la noticia, y el
veredicto salió `deceptive`.
"""

import pytest
from pydantic import BaseModel

from backend.core.texto import TextoOpcional


class _ConTexto(BaseModel):
    texto: TextoOpcional = None


@pytest.mark.parametrize(
    "ausente",
    [None, "", "   ", "\n\t", "None", "none", "NONE", " None ", "null", "Null"],
)
def test_la_ausencia_escrita_como_texto_es_ausencia(ausente):
    assert _ConTexto(texto=ausente).texto is None


@pytest.mark.parametrize(
    "presente",
    [
        "None of Us Knew",
        "Nonetheless, markets rallied",
        "A small trial found modest effects in mice",
        "nullify",
    ],
)
def test_un_texto_que_empieza_igual_sigue_siendo_texto(presente):
    """Sólo la palabra sola: un titular o un cuerpo que la contienen son texto."""
    assert _ConTexto(texto=presente).texto == presente


def test_el_esquema_no_cambia():
    """Ni el contrato REST ni lo que lee el modelo cambian: sigue siendo texto o
    nada. El tipo corrige lo que llega, no lo que se pide."""
    esquema = _ConTexto.model_json_schema()["properties"]["texto"]
    assert esquema["anyOf"] == [{"type": "string"}, {"type": "null"}]
