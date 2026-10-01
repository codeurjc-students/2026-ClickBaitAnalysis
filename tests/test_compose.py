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


def test_la_api_no_publica_ningun_puerto():
    """La condición que sostiene el límite por cliente de #169.

    Detrás de Caddy, quién es el cliente sale de `X-Forwarded-For`, y esa
    cabecera sólo es creíble porque a la API no se llega si no es por el proxy,
    que la sobrescribe con la dirección real. Publicar el 8000 —aunque fuera
    sólo en `127.0.0.1`, como se hizo para probar en #163— devolvería a
    cualquiera la posibilidad de declararse quien quiera y estrenar cupo en
    cada petición.
    """
    assert "ports" not in _servicios()["api"]


def test_la_api_se_fia_de_las_cabeceras_del_proxy():
    """Sin esto uvicorn IGNORA `X-Forwarded-For` —sólo se fía de `127.0.0.1`—
    y todas las peticiones parecen venir del contenedor de Caddy: el límite de
    #169 pasaría a ser uno solo, compartido por todo internet."""
    assert "--forwarded-allow-ips" in _servicios()["api"]["command"]


def test_el_servicio_de_la_api_se_llama_api():
    """Contrato con `docker/Caddyfile`, que reenvía a `api:8000` (#163): dentro
    de compose, el nombre del servicio es su dirección."""
    assert "api" in _servicios()


def test_la_api_alcanza_el_tunel_del_agente():
    """Contrato con el túnel inverso de #181, que escucha en 172.17.0.1:11434
    del host (`despliegue/maquina1/70-tunel.conf`).

    Para un contenedor, `127.0.0.1` es él mismo: el host se alcanza como
    `host.docker.internal`, y ese nombre sólo existe con `host-gateway`. Sin él,
    el agente daría «no pudo contactar» con la sesión abierta y el túnel bien.
    """
    api = _servicios()["api"]

    assert "host.docker.internal:host-gateway" in api.get("extra_hosts", [])
    assert api["environment"]["LLM_BACKEND"] == "ollama"
    assert api["environment"]["LLM_URL"].startswith("http://host.docker.internal:")
