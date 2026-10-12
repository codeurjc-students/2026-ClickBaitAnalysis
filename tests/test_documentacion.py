"""Lo que las guías del repositorio tienen que decir de la configuración (#251).

`docs/ejecucion.md` lista cada ajuste de `settings` con su valor por defecto,
y una tabla así caduca sin avisar: #235 añadió dos claves, y #93, #159 y #230,
otros ajustes. Igual `.env.example`. Aquí se comprueba contra `Settings`, que
es la única fuente: si un campo nuevo no está en la guía, o la guía nombra uno
que ya no existe, falla.

Prueba el repositorio en sí, no un módulo, como `test_arquitectura.py` y
`test_compose.py`.
"""

import re
from pathlib import Path

from backend.config.settings import Settings

RAIZ = Path(__file__).resolve().parents[1]
EJECUCION = RAIZ / "docs" / "ejecucion.md"
ENV_EJEMPLO = RAIZ / ".env.example"

# Una variable de entorno escrita como código: `NLP_MODELS`, `HF_TOKEN`.
VARIABLE_EN_LA_GUIA = re.compile(r"`([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)`")


def _variables_de_settings() -> set[str]:
    # pydantic-settings lee cada campo de la variable con su nombre, sin
    # distinguir mayúsculas: `nlp_models` sale de `NLP_MODELS`.
    return {campo.upper() for campo in Settings.model_fields}


def test_la_guia_de_ejecucion_nombra_cada_ajuste():
    nombradas = set(VARIABLE_EN_LA_GUIA.findall(EJECUCION.read_text(encoding="utf-8")))

    assert sorted(_variables_de_settings() - nombradas) == []


def test_la_guia_de_ejecucion_no_nombra_ajustes_que_no_existen():
    nombradas = set(VARIABLE_EN_LA_GUIA.findall(EJECUCION.read_text(encoding="utf-8")))

    assert sorted(nombradas - _variables_de_settings()) == []


def test_env_example_solo_trae_ajustes_que_existen():
    variables = {
        linea.split("=", 1)[0].strip()
        for linea in ENV_EJEMPLO.read_text(encoding="utf-8").splitlines()
        if "=" in linea and not linea.lstrip().startswith("#")
    }

    assert variables, "no se leyó ninguna variable de .env.example"
    assert sorted(variables - _variables_de_settings()) == []
