"""Tests de los prompts versionados del agente (#188, R13.5)."""

from typing import get_args

import pytest

from backend.agent import prompts
from backend.config.settings import Settings


def test_el_ajuste_que_elige_el_prompt_ofrece_los_versionados():
    """`llm_prompt` es un `Literal` para que un nombre mal escrito falle al
    arrancar (#189). El precio es que un prompt nuevo hay que añadirlo en dos
    sitios, y esto dice cuándo se ha olvidado uno."""
    ofrecidos = get_args(Settings.model_fields["llm_prompt"].annotation)
    assert sorted(ofrecidos) == prompts.disponibles()


def test_los_prompts_versionados_se_pueden_cargar():
    assert prompts.disponibles() == ["03-estricto", "04-preciso"]
    for nombre in prompts.disponibles():
        assert prompts.cargar(nombre).startswith("Eres el asistente")


def test_un_prompt_que_no_existe_se_dice_junto_con_los_que_hay():
    with pytest.raises(ValueError, match="04-preciso"):
        prompts.cargar("99-inventado")


@pytest.mark.parametrize("nombre", prompts.disponibles())
def test_ningun_prompt_llama_zero_shot_a_la_caja_negra(nombre):
    """`detect_clickbait` dejó de ser zero-shot en #115, y los prompts del spike
    lo seguían diciendo. Es lo primero que lee el modelo en cada petición."""
    assert "zero-shot" not in prompts.cargar(nombre).lower()
