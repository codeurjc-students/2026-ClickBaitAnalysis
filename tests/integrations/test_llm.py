"""Tests del cliente del modelo de lenguaje (#187), con Ollama simulado.

Ninguno necesita un Ollama de verdad: `respx` sustituye el transporte. Lo que se
comprueba es lo que este código decide —qué envía, cómo lee y qué publica—, no
el modelo. Contra la A40 se comprueba aparte, con `spikes/llm_disponibilidad.sh`.
"""

import json
import socket

import httpx
import pytest
import respx
from httpx import Response
from structlog.testing import capture_logs

from backend.config.settings import settings
from backend.integrations.llm import factory
from backend.integrations.llm.model_card import FICHA
from backend.integrations.llm.ollama import OllamaClient

URL = "http://ollama.prueba:11434"


def _cliente(modelo: str = "qwen3.5:27b") -> OllamaClient:
    return OllamaClient(URL, modelo, num_ctx=8192, keep_alive="10m", timeout=30.0)


HERRAMIENTA = {
    "name": "detect_clickbait_lexical",
    "description": "Pistas léxicas del titular.",
    "parameters": {"type": "object", "properties": {"headline": {"type": "string"}}},
}


def _respuesta_ollama(**mensaje) -> dict:
    return {
        "message": {"role": "assistant", "content": "", **mensaje},
        "prompt_eval_count": 2641,
        "eval_count": 12,
        "load_duration": 8_600_000_000,
        "total_duration": 9_000_000_000,
    }


# ----- Lo que se envía -----


@pytest.mark.asyncio
async def test_el_chat_envia_num_ctx_explicito_y_la_conversacion_traducida():
    mensajes = [
        {"role": "system", "content": "Eres un asistente."},
        {"role": "user", "content": "¿Es clickbait 'You Won't Believe This'?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"name": "detect_clickbait_lexical", "arguments": {"headline": "x"}}
            ],
        },
        {"role": "tool", "tool_name": "detect_clickbait_lexical", "content": "{}"},
    ]
    with respx.mock:
        ruta = respx.post(f"{URL}/api/chat").mock(
            return_value=Response(200, json=_respuesta_ollama(content="Sí."))
        )
        await _cliente().chat(mensajes, [HERRAMIENTA])

    enviado = json.loads(ruta.calls.last.request.content)
    # `num_ctx` SIEMPRE explícito: el defecto de Ollama depende de la VRAM (#181).
    assert enviado["options"] == {"num_ctx": 8192}
    assert enviado["model"] == "qwen3.5:27b"
    assert enviado["stream"] is False
    assert enviado["think"] is False
    assert enviado["keep_alive"] == "10m"
    assert enviado["tools"] == [
        {
            "type": "function",
            "function": {
                "name": HERRAMIENTA["name"],
                "description": HERRAMIENTA["description"],
                "parameters": HERRAMIENTA["parameters"],
            },
        }
    ]
    asistente, herramienta = enviado["messages"][2], enviado["messages"][3]
    assert asistente["tool_calls"] == [
        {
            "function": {
                "name": "detect_clickbait_lexical",
                "arguments": {"headline": "x"},
            }
        }
    ]
    assert herramienta == {
        "role": "tool",
        "content": "{}",
        "tool_name": "detect_clickbait_lexical",
    }


@pytest.mark.asyncio
async def test_sin_herramientas_no_se_envia_la_clave_tools():
    with respx.mock:
        ruta = respx.post(f"{URL}/api/chat").mock(
            return_value=Response(200, json=_respuesta_ollama(content="Hola."))
        )
        await _cliente().chat([{"role": "user", "content": "hola"}], [])

    assert "tools" not in json.loads(ruta.calls.last.request.content)


# ----- Lo que se lee -----


@pytest.mark.asyncio
async def test_el_chat_lee_las_llamadas_y_las_medidas():
    llamada = {
        "function": {"name": "detect_clickbait_linear", "arguments": {"headline": "x"}}
    }
    with respx.mock:
        respx.post(f"{URL}/api/chat").mock(
            return_value=Response(200, json=_respuesta_ollama(tool_calls=[llamada]))
        )
        resultado = await _cliente().chat([{"role": "user", "content": "?"}], [])

    assert resultado.success
    assert resultado.data == {
        "content": "",
        "tool_calls": [
            {"name": "detect_clickbait_linear", "arguments": {"headline": "x"}}
        ],
        "metrics": {
            "prompt_tokens": 2641,
            "output_tokens": 12,
            "load_s": 8.6,
            "total_s": 9.0,
        },
    }


@pytest.mark.asyncio
async def test_los_argumentos_en_texto_json_tambien_se_leen():
    llamada = {"function": {"name": "f", "arguments": '{"headline": "x"}'}}
    with respx.mock:
        respx.post(f"{URL}/api/chat").mock(
            return_value=Response(200, json=_respuesta_ollama(tool_calls=[llamada]))
        )
        resultado = await _cliente().chat([{"role": "user", "content": "?"}], [])

    assert resultado.unwrap()["tool_calls"] == [
        {"name": "f", "arguments": {"headline": "x"}}
    ]


@pytest.mark.asyncio
async def test_sin_recuento_de_tokens_no_se_inventa_un_cero():
    datos = _respuesta_ollama(content="ok")
    del datos["prompt_eval_count"]
    with respx.mock:
        respx.post(f"{URL}/api/chat").mock(return_value=Response(200, json=datos))
        resultado = await _cliente().chat([{"role": "user", "content": "?"}], [])

    assert resultado.unwrap()["metrics"]["prompt_tokens"] is None


# ----- Lo que se publica cuando falla -----


@pytest.mark.asyncio
async def test_un_error_http_no_publica_el_cuerpo_del_servidor():
    with respx.mock:
        respx.post(f"{URL}/api/chat").mock(
            return_value=Response(404, json={"error": "model 'qwen3.5:27b' not found"})
        )
        resultado = await _cliente().chat([{"role": "user", "content": "?"}], [])

    assert not resultado.success
    assert "404" in resultado.error
    assert "model 'qwen3.5:27b'" not in resultado.error


@pytest.mark.asyncio
async def test_un_timeout_se_describe_sin_el_texto_de_la_libreria():
    with respx.mock:
        respx.post(f"{URL}/api/chat").mock(
            side_effect=httpx.ReadTimeout("lectura agotada")
        )
        resultado = await _cliente().chat([{"role": "user", "content": "?"}], [])

    assert not resultado.success
    assert "tardó demasiado" in resultado.error
    assert "lectura agotada" not in resultado.error


MARCA_DEL_SERVIDOR = "detalle-interno-del-servidor"


@pytest.mark.asyncio
async def test_una_respuesta_inesperada_se_registra_y_no_se_publica():
    """La regla de #185: un fallo que viaja como valor lo sanea quien lo crea."""
    with respx.mock, capture_logs() as registrado:
        respx.post(f"{URL}/api/chat").mock(
            return_value=Response(200, json={"inesperado": MARCA_DEL_SERVIDOR})
        )
        resultado = await _cliente().chat([{"role": "user", "content": "?"}], [])

    assert not resultado.success
    assert MARCA_DEL_SERVIDOR not in resultado.error
    assert "qwen3.5:27b" in resultado.error
    fallo = next(
        linea for linea in registrado if linea["event"] == "llm.respuesta_inesperada"
    )
    assert MARCA_DEL_SERVIDOR in fallo["respuesta"]


# ----- Disponibilidad: los cuatro estados de R6.14 -----


def _puerto_sin_nadie() -> int:
    """Un puerto local libre: quien se conecte recibirá un rechazo de verdad."""
    with socket.socket() as enchufe:
        enchufe.bind(("127.0.0.1", 0))
        return enchufe.getsockname()[1]


@pytest.mark.asyncio
async def test_una_conexion_rechazada_es_la_sesion_cerrada():
    """Con un puerto REAL sin nadie, no con `respx`: al lanzar un efecto
    simulado, `respx` sustituye su causa por la suya, y lo que se prueba aquí es
    justo la causa. La cadena que da httpx de verdad es `ConnectError →
    ConnectError → OSError → ConnectionRefusedError`."""
    cliente = OllamaClient(
        f"http://127.0.0.1:{_puerto_sin_nadie()}",
        "qwen3.5:27b",
        num_ctx=8192,
        keep_alive="10m",
        timeout=30.0,
    )

    estado = await cliente.disponibilidad()

    assert estado.status == "unreachable"
    assert "bajo demanda" in estado.detail


@pytest.mark.asyncio
async def test_otro_fallo_de_conexion_no_se_hace_pasar_por_sesion_cerrada():
    """Un nombre que no resuelve también es `ConnectError`, pero es un fallo de
    configuración: decir «está apagado» sería mentir."""
    with respx.mock:
        respx.get(f"{URL}/api/version").mock(
            side_effect=httpx.ConnectError("Name or service not known")
        )
        estado = await _cliente().disponibilidad()

    assert estado.status == "unreachable"
    assert "bajo demanda" not in estado.detail
    assert "Name or service" not in estado.detail


@pytest.mark.asyncio
async def test_sin_el_modelo_descargado():
    with respx.mock:
        respx.get(f"{URL}/api/version").mock(
            return_value=Response(200, json={"version": "0.34.2"})
        )
        respx.get(f"{URL}/api/tags").mock(
            return_value=Response(200, json={"models": [{"name": "qwen3.5:2b"}]})
        )
        estado = await _cliente().disponibilidad()

    assert estado.status == "model_missing"
    assert "qwen3.5:27b" in estado.detail


@pytest.mark.asyncio
async def test_disponible_con_el_modelo_descargado():
    with respx.mock:
        respx.get(f"{URL}/api/version").mock(
            return_value=Response(200, json={"version": "0.34.2"})
        )
        respx.get(f"{URL}/api/tags").mock(
            return_value=Response(200, json={"models": [{"name": "qwen3.5:27b"}]})
        )
        estado = await _cliente().disponibilidad()

    assert estado.status == "available"
    assert estado.model == "qwen3.5:27b"


@pytest.mark.asyncio
async def test_un_modelo_sin_etiqueta_es_el_latest():
    with respx.mock:
        respx.get(f"{URL}/api/version").mock(
            return_value=Response(200, json={"version": "0.34.2"})
        )
        respx.get(f"{URL}/api/tags").mock(
            return_value=Response(200, json={"models": [{"name": "qwen3.5:latest"}]})
        )
        estado = await _cliente("qwen3.5").disponibilidad()

    assert estado.status == "available"


# ----- La factoría -----


@pytest.mark.asyncio
async def test_sin_configurar_no_hay_backend(monkeypatch):
    monkeypatch.setattr(settings, "llm_backend", None)

    assert factory.get_llm_backend() is None
    estado = await factory.disponibilidad()
    assert estado.status == "not_configured"


def test_el_backend_se_cachea_por_el_valor_de_la_configuracion(monkeypatch):
    """#119: cambiar un ajuste da otro cliente; repetirlo, el mismo."""
    monkeypatch.setattr(settings, "llm_backend", "ollama")
    monkeypatch.setattr(settings, "llm_url", URL)
    monkeypatch.setattr(settings, "llm_model", "qwen3.5:27b")
    primero = factory.get_llm_backend()

    assert isinstance(primero, OllamaClient)
    assert primero.model == "qwen3.5:27b"
    assert factory.get_llm_backend() is primero

    monkeypatch.setattr(settings, "llm_model", "qwen3.5:2b")
    otro = factory.get_llm_backend()
    assert isinstance(otro, OllamaClient)
    assert otro is not primero
    assert otro.model == "qwen3.5:2b"


def test_la_ficha_declarada_se_publica_con_su_modelo(monkeypatch):
    monkeypatch.setattr(settings, "llm_model", FICHA["model_id"])

    assert factory.ficha_efectiva() == FICHA


def test_con_otro_modelo_las_medidas_dejan_de_publicarse(monkeypatch):
    """#119: las limitaciones medidas eran de otro modelo."""
    monkeypatch.setattr(settings, "llm_model", "otro:7b")

    ficha = factory.ficha_efectiva()

    assert ficha["model_id"] == "otro:7b"
    assert ficha["type"] == "opaque"
    assert ficha["task"] == FICHA["task"]
    assert len(ficha["limitations"]) == 1
    assert ficha["limitations"][0].startswith("SIN EVALUAR")
