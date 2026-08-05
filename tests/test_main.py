"""Tests del arranque del servidor MCP (R1.6).

`mcp.run()` bloquea el proceso, así que en todos estos tests se sustituye por un
doble que sólo anota con qué se le llamó.
"""

import pytest
from pydantic import ValidationError

from backend import main as main_mod
from backend.config.settings import Settings, settings

_CLAVES = {"guardian_api_key": "x", "nyt_api_key": "x", "hf_token": "x"}


@pytest.fixture
def run_espia(monkeypatch):
    """Sustituye `mcp.run` y devuelve un dict con los argumentos recibidos."""
    recibido = {}
    monkeypatch.setattr(
        main_mod.mcp, "run", lambda transport: recibido.update(transport=transport)
    )
    monkeypatch.setattr(main_mod.mcp.settings, "host", "sin-tocar")
    monkeypatch.setattr(main_mod.mcp.settings, "port", 0)
    return recibido


def test_el_transporte_por_defecto_es_stdio():
    assert Settings.model_fields["mcp_transport"].default == "stdio"


def test_main_arranca_con_el_transporte_configurado(monkeypatch, run_espia):
    monkeypatch.setattr(settings, "mcp_transport", "streamable-http")

    main_mod.main()

    assert run_espia["transport"] == "streamable-http"


def test_main_propaga_host_y_puerto_al_servidor(monkeypatch, run_espia):
    monkeypatch.setattr(settings, "mcp_host", "0.0.0.0")
    monkeypatch.setattr(settings, "mcp_port", 9999)

    main_mod.main()

    assert main_mod.mcp.settings.host == "0.0.0.0"
    assert main_mod.mcp.settings.port == 9999


def test_un_transporte_desconocido_se_rechaza_al_arrancar():
    # La validación ocurre al construir Settings, no al llamar a mcp.run(): así
    # una configuración mal escrita falla en el arranque y no a mitad de uso.
    with pytest.raises(ValidationError):
        Settings(mcp_transport="websocket", **_CLAVES)


@pytest.mark.parametrize("transporte", ["stdio", "streamable-http"])
# Prueba con uno, luego con otro
def test_ambos_transportes_son_validos(transporte):
    assert Settings(mcp_transport=transporte, **_CLAVES).mcp_transport == transporte
