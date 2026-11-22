"""La grabación de la demostración sigue siendo la de la guía (#265).

El plan B de la defensa reproduce `backend/integrations/llm/grabaciones/
demostracion.json`, la conversación del paso 6 de `docs/demostracion.md`
grabada con el 27B. El reproductor sólo narra lo grabado si el último turno del
usuario es una consulta grabada y si el prompt de sistema es, letra a letra, el
de la grabación (`grabado.py`). Las dos cosas pueden dejar de cumplirse sin que
nada falle hasta la sala:

- la guía dice qué se pega en el paso 6: si se cambia una pregunta, la grabada
  ya no se encuentra, y el asistente contesta que no está grabada;
- y si se toca el prompt en uso, o cambia el de por defecto, el reproductor se
  niega a narrar.

Lo que no se comprueba aquí son los resultados de las herramientas, que piden
los modelos: eso lo hace `spikes/grabar_demostracion.py --reproducir`, también
la víspera de la defensa.

Prueba el repositorio en sí, no un módulo, como `test_ejemplos_formulario.py`.
"""

import re
from pathlib import Path

from pydantic import TypeAdapter

from backend.agent import prompts
from backend.config.settings import Settings
from backend.integrations.llm.grabado import CARPETA, Grabacion

RAIZ = Path(__file__).resolve().parents[1]
GUIA = RAIZ / "docs" / "demostracion.md"
GRABACION = CARPETA / "demostracion.json"

# La misma marca con la que las lee `spikes/grabar_demostracion.py` al grabar.
MARCA = "Las tres preguntas del paso 6:"


def _grabacion() -> Grabacion:
    return TypeAdapter(Grabacion).validate_json(GRABACION.read_bytes())


def _preguntas_de_la_guia() -> list[str]:
    """Los tres bloques `text` que siguen a la marca, tal cual."""
    texto = GUIA.read_text(encoding="utf-8")
    assert texto.count(MARCA) == 1, f"La guía tiene que llevar una vez «{MARCA}»."
    despues = texto.split(MARCA, 1)[1]
    return re.findall(r"```text\n(.*?)\n```", despues, re.DOTALL)[:3]


def test_la_grabacion_se_puede_leer():
    """Si no, el asistente saldría como no disponible (`model_missing`)."""
    _grabacion()


def test_sus_consultas_son_las_tres_preguntas_del_paso_6():
    consultas = [turno["query"] for turno in _grabacion()["turns"]]
    assert consultas == _preguntas_de_la_guia()


def test_su_prompt_es_el_de_por_defecto_y_no_ha_cambiado():
    """El de por defecto, y no el del `.env` de quien ejecuta la prueba:
    `compose.yaml` no fija `LLM_PROMPT`, así que la API sirve ése."""
    prompt = _grabacion()["prompt"]
    assert prompt["name"] == Settings.model_fields["llm_prompt"].default
    assert prompt["text"] == prompts.cargar(prompt["name"])
