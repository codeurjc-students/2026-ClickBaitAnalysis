"""Tests del arranque del servidor MCP (R1.6).

`mcp.run()` bloquea el proceso, así que en todos estos tests se sustituye por un
doble que sólo anota con qué se le llamó.
"""

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import ValidationError

from backend import main as main_mod
from backend.config.settings import Settings, settings

_CLAVES = {"guardian_api_key": "x", "nyt_api_key": "x", "hf_token": "x"}

# El Host DEBE llevar puerto: la protección anti DNS-rebinding de FastMCP acepta
# `127.0.0.1:*`, y ASGITransport enviaría `Host: 127.0.0.1` pelado, que no casa
# y se rechaza con 421. Se deja la protección activa en vez de desactivarla.
_BASE = "http://127.0.0.1:8765"


@pytest.fixture
def run_espia(monkeypatch):
    """Sustituye `mcp.run` y devuelve un dict con los argumentos recibidos."""
    recibido = {}
    monkeypatch.setattr(
        main_mod.mcp, "run", lambda transport: recibido.update(transport=transport)
    )
    monkeypatch.setattr(main_mod.mcp.settings, "host", "sin-tocar")
    monkeypatch.setattr(main_mod.mcp.settings, "port", 0)
    # `configurar_red` puede quitarle la protección al singleton: se restaura
    # para que no llegue cambiada a otros tests.
    monkeypatch.setattr(
        main_mod.mcp.settings,
        "transport_security",
        main_mod.mcp.settings.transport_security,
    )
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


# ----- La protección contra DNS rebinding (#164) -----

_INICIO = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "prueba", "version": "0"},
    },
}
_CABECERAS_MCP = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


async def _iniciar_sesion_como(servidor, direccion: str) -> int:
    """Manda un `initialize` en memoria, con la cabecera `Host` de `direccion`.

    Es la misma petición que se midió en la VM. La app se construye DESPUÉS de
    configurar la red: FastMCP lee la protección al construirla.
    """
    app = servidor.streamable_http_app()
    transporte = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transporte, base_url=direccion) as http_client,
    ):
        respuesta = await http_client.post("/mcp", json=_INICIO, headers=_CABECERAS_MCP)
    return respuesta.status_code


@pytest.mark.asyncio
async def test_escuchando_en_la_red_acepta_el_nombre_del_servicio(servidor_mcp):
    """El fallo de #164. Dentro de compose la API llama al MCP como
    `http://mcp:8765`, y con la protección que FastMCP activa al construirse la
    respuesta era `421 Invalid Host header`: cambiar el host a `0.0.0.0` después
    no la recalculaba."""
    main_mod.configurar_red(servidor_mcp, "0.0.0.0", 8765)

    assert await _iniciar_sesion_como(servidor_mcp, "http://mcp:8765") == 200


@pytest.mark.asyncio
async def test_escuchando_en_local_la_proteccion_se_mantiene(servidor_mcp):
    """La otra mitad: en desarrollo el servidor escucha en local y la protección
    sigue activa. Si la librería cambiara su regla, esto avisa."""
    main_mod.configurar_red(servidor_mcp, "127.0.0.1", 8765)

    assert await _iniciar_sesion_como(servidor_mcp, "http://mcp:8765") == 421


def test_un_transporte_desconocido_se_rechaza_al_arrancar():
    # La validación ocurre al construir Settings, no al llamar a mcp.run(): así
    # una configuración mal escrita falla en el arranque y no a mitad de uso.
    with pytest.raises(ValidationError):
        Settings(mcp_transport="websocket", **_CLAVES)


@pytest.mark.parametrize("transporte", ["stdio", "streamable-http"])
# Prueba con uno, luego con otro
def test_ambos_transportes_son_validos(transporte):
    assert Settings(mcp_transport=transporte, **_CLAVES).mcp_transport == transporte


@pytest.mark.asyncio
async def test_el_servidor_sirve_de_verdad_por_http(servidor_mcp):
    """El servidor responde el protocolo MCP completo por HTTP.

    Los tests de arriba espían `mcp.run`, así que comprueban el CABLEADO pero no
    que el servidor sirva. Éste sí: habla el protocolo real —handshake,
    `list_tools`, `call_tool`— contra la app ASGI **en el mismo proceso**.

    Sin puerto ni subproceso: al cliente MCP se le pasa un `httpx.AsyncClient`
    montado sobre `ASGITransport`, así que las peticiones entran directas en la
    app sin tocar la red.
    """
    # Servidor recién construido, no el singleton de main: su gestor de
    # sesiones sólo puede arrancar una vez por instancia (ver conftest).
    app = servidor_mcp.streamable_http_app()
    transporte = httpx.ASGITransport(app=app)

    # El gestor de sesiones de FastMCP arranca en el lifespan de la app, y
    # ASGITransport no lo ejecuta: hay que entrar a mano o toda petición falla.
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transporte, base_url=_BASE) as http_client,
        streamable_http_client(f"{_BASE}/mcp", http_client=http_client) as (
            read,
            write,
            _,
        ),
        # Basicamente, gestión de tubería bidireccional, necesario con streamable porque MCP necesita stream continuo
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            assert {t.name for t in tools.tools} >= {
                "detect_clickbait_lexical",
                "health_check",
            }
            lexical = next(
                t for t in tools.tools if t.name == "detect_clickbait_lexical"
            )
            assert lexical.description
            assert "headline" in lexical.inputSchema["properties"]

            # Y ejecutar de verdad, no sólo enumerar. Se elige una tool
            # local y determinista: no toca red ni carga modelos.
            resultado = await session.call_tool(
                "detect_clickbait_lexical",
                {"headline": "10 Things You Won't Believe"},
            )
            assert '"is_clickbait": true' in resultado.content[0].text
