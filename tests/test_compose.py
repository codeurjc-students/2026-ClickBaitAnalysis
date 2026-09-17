"""Contratos del `compose.yaml` que ningún otro test ve (#164).

El CI no levanta contenedores, así que un error de configuración del despliegue
sólo aparece desplegando. Estos dos ya costaron algo, y se fijan leyendo el
fichero.

PyYAML no está en `requirements.in`: llega al lockfile como dependencia de
`fastmcp` y de `huggingface-hub`. Si un día desaparece, esto falla al importar —
ruidoso, no en silencio.
"""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[1] / "compose.yaml"


def _servicios() -> dict:
    # `safe_load` resuelve las anclas y los `<<:`, así que se lee lo mismo que
    # lee compose, no lo que está escrito en cada servicio.
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def test_todo_proceso_del_backend_ejecuta_las_senales_en_local():
    """El fallo de #164. Los DOS procesos del backend ejecutan señales NLP —la
    API desde `/analyze` y el MCP desde sus herramientas—, y `NLP_BACKEND`
    estaba sólo en la API: el MCP arrancaba con `remote` y `detect_clickbait`
    daba el 400 de #156 desde la pantalla de Sistema."""
    del_backend = {
        nombre: servicio
        for nombre, servicio in _servicios().items()
        if servicio.get("image") == "clickbait-backend"
    }

    assert set(del_backend) == {"api", "mcp"}
    for nombre, servicio in del_backend.items():
        assert servicio["environment"].get("NLP_BACKEND") == "local", nombre


def test_el_servicio_de_la_api_se_llama_api():
    """Contrato con `docker/Caddyfile`, que reenvía a `api:8000` (#163): dentro
    de compose, el nombre del servicio es su dirección."""
    assert "api" in _servicios()
