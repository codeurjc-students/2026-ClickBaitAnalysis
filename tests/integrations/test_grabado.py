"""Tests del backend que reproduce respuestas grabadas (#265).

Se llama a `chat()` con las conversaciones que le mandaría el agente, sin el
bucle ni MCP: lo que se prueba es qué reproduce y cuándo se niega. Que el bucle
ejecute de verdad lo que pide una vuelta grabada lo prueba
`tests/agent/test_agente.py`.

La grabación es pequeña y está escrita aquí: dos turnos, uno con una vuelta
cortada (#208), y resultados con una cifra, un texto y un booleano, que son las
tres cosas que la comparación trata distinto.
"""

import copy
import json
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from backend.agent.agente import PEDIR_RESPUESTA
from backend.integrations.llm.base import Mensaje
from backend.integrations.llm.grabado import (
    HA_CAMBIADO,
    SIN_GRABACION,
    ReproductorGrabado,
    normalizar,
)

PROMPT = "Eres el asistente de prueba."

CONSULTA_1 = "Analiza el titular 'You Won't Believe This'"
CONSULTA_2 = "¿Con qué peso contribuye cada palabra de 'You Won't Believe This'?"

ANALISIS = {"verdict": "stylistic_clickbait", "probability": 0.951, "decided": True}
PESOS = {"probability": 0.994, "top_cues": [["you", 1.75], ["believe", 0.42]]}

NARRACION_1 = "Es clickbait de forma: la dedicada da 0,951."
NARRACION_2 = "Lo que más pesa es «you», con 1,75."

MEDIDAS = {"prompt_tokens": 3100, "output_tokens": 240, "load_s": 0.1, "total_s": 9.5}


def _vuelta(resultados: list[tuple[str, dict]], **respuesta) -> dict:
    """Una vuelta grabada: los resultados que recibió y lo que respondió."""
    return {
        "tool_results": [
            {"tool_name": nombre, "content": json.dumps(datos, ensure_ascii=False)}
            for nombre, datos in resultados
        ],
        "response": {
            "content": "",
            "tool_calls": [],
            "metrics": MEDIDAS,
            "cortada": False,
            **respuesta,
        },
    }


GRABACION = {
    "model": "qwen3.5:27b",
    "model_digest": "7653528ba5cb",
    "recorded_at": "2026-11-13",
    "commit": "abc1234",
    "prompt": {"name": "06-dato", "text": PROMPT},
    "takes": {"recorded": 3, "chosen": 2},
    "conditions": {"num_ctx": 16384},
    "turns": [
        {
            "query": CONSULTA_1,
            "rounds": [
                _vuelta(
                    [],
                    tool_calls=[
                        {
                            "name": "analyze_headline",
                            "arguments": {"headline": "You Won't Believe This"},
                        }
                    ],
                ),
                _vuelta([("analyze_headline", ANALISIS)], content=NARRACION_1),
            ],
        },
        {
            "query": CONSULTA_2,
            "rounds": [
                _vuelta(
                    [],
                    tool_calls=[
                        {
                            "name": "detect_clickbait_linear",
                            "arguments": {"headline": "You Won't Believe This"},
                        }
                    ],
                ),
                # El tope de salida la cortó a media frase, y el agente le
                # pidió la respuesta: es la vuelta siguiente (#208).
                _vuelta(
                    [("detect_clickbait_linear", PESOS)],
                    content="Lo que más pe",
                    cortada=True,
                ),
                _vuelta([], content=NARRACION_2),
            ],
        },
    ],
}


@pytest.fixture
def reproductor(tmp_path: Path) -> ReproductorGrabado:
    ruta = tmp_path / "demostracion.json"
    ruta.write_text(json.dumps(GRABACION, ensure_ascii=False), encoding="utf-8")
    return ReproductorGrabado(ruta)


def _mensajes(
    consulta: str,
    *despues: Mensaje,
    historial: tuple[Mensaje, ...] = (),
    prompt: str = PROMPT,
) -> list[Mensaje]:
    """La conversación como la monta el agente: prompt, historial, consulta y
    lo que haya pasado ya en este turno."""
    return [
        {"role": "system", "content": prompt},
        *historial,
        {"role": "user", "content": consulta},
        *despues,
    ]


def _pidio(nombre: str, argumentos: dict) -> Mensaje:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"name": nombre, "arguments": argumentos}],
    }


def _devuelve(nombre: str, datos: dict) -> Mensaje:
    return {
        "role": "tool",
        "tool_name": nombre,
        "content": json.dumps(datos, ensure_ascii=False),
    }


PIDE_ANALISIS = _pidio("analyze_headline", {"headline": "You Won't Believe This"})


async def _responde(reproductor: ReproductorGrabado, mensajes: list[Mensaje]) -> dict:
    resultado = await reproductor.chat(mensajes, [], think=True)
    assert resultado.success
    return resultado.unwrap()


# ----- Lo que reproduce -----


@pytest.mark.asyncio
async def test_reproduce_las_herramientas_que_pidio_con_sus_argumentos(reproductor):
    respuesta = await _responde(reproductor, _mensajes(CONSULTA_1))

    assert respuesta["tool_calls"] == [
        {
            "name": "analyze_headline",
            "arguments": {"headline": "You Won't Believe This"},
        }
    ]
    # Las medidas son las del día que se grabó: lo que costó de verdad.
    assert respuesta["metrics"] == MEDIDAS
    assert respuesta["cortada"] is False


@pytest.mark.asyncio
async def test_con_el_resultado_grabado_reproduce_la_narracion(reproductor):
    respuesta = await _responde(
        reproductor,
        _mensajes(CONSULTA_1, PIDE_ANALISIS, _devuelve("analyze_headline", ANALISIS)),
    )

    assert respuesta["content"] == NARRACION_1
    assert respuesta["tool_calls"] == []


@pytest.mark.asyncio
async def test_una_vuelta_cortada_se_reproduce_y_despues_la_que_se_pidio(reproductor):
    """La vuelta se cuenta por las respuestas del modelo desde la consulta,
    también la cortada a la que sigue `PEDIR_RESPUESTA` (#208)."""
    pide_pesos = _pidio(
        "detect_clickbait_linear", {"headline": "You Won't Believe This"}
    )
    pesos = _devuelve("detect_clickbait_linear", PESOS)

    cortada = await _responde(reproductor, _mensajes(CONSULTA_2, pide_pesos, pesos))
    assert cortada["cortada"] is True

    pedida = await _responde(
        reproductor,
        _mensajes(
            CONSULTA_2,
            pide_pesos,
            pesos,
            {"role": "assistant", "content": cortada["content"]},
            {"role": "system", "content": PEDIR_RESPUESTA},
        ),
    )
    assert pedida["content"] == NARRACION_2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "historial",
    [
        (),
        (
            {"role": "user", "content": CONSULTA_1},
            {"role": "assistant", "content": NARRACION_1},
            {"role": "system", "content": "Aviso del historial."},
        ),
    ],
    ids=["sin-historial", "con-historial"],
)
async def test_busca_por_el_ultimo_turno_con_o_sin_historial(reproductor, historial):
    """La pantalla recorta el historial quitando los turnos más antiguos, y
    empezar una conversación nueva lo vacía: el turno 2 tiene que reproducirse
    igual. Lo que narra se sigue comprobando, con los resultados de este turno."""
    respuesta = await _responde(reproductor, _mensajes(CONSULTA_2, historial=historial))

    assert respuesta["tool_calls"][0]["name"] == "detect_clickbait_linear"


@pytest.mark.asyncio
async def test_la_consulta_se_busca_sin_mayusculas_espacios_ni_comillas_tipograficas(
    reproductor,
):
    pegada = "  analiza el   TITULAR ‘You Won’t Believe This’ "

    respuesta = await _responde(reproductor, _mensajes(pegada))

    assert respuesta["tool_calls"][0]["name"] == "analyze_headline"
    assert normalizar(pegada) == normalizar(CONSULTA_1)


@pytest.mark.asyncio
async def test_la_grabacion_queda_intacta_aunque_se_toque_lo_devuelto(reproductor):
    primera = await _responde(reproductor, _mensajes(CONSULTA_1))
    original = copy.deepcopy(primera)
    primera["tool_calls"].append({"name": "otra", "arguments": {}})
    primera["tool_calls"][0]["arguments"]["headline"] = "cambiado"

    segunda = await _responde(reproductor, _mensajes(CONSULTA_1))

    assert segunda == original


@pytest.mark.asyncio
@pytest.mark.parametrize("probabilidad", [0.950, 0.952], ids=["-0,001", "+0,001"])
async def test_una_cifra_que_se_mueve_una_milesima_se_reproduce(
    reproductor, probabilidad
):
    """El agente redondea a tres decimales lo que lee el modelo, y otro equipo
    puede redondear distinto en la tercera cifra."""
    movido = {**ANALISIS, "probability": probabilidad}

    respuesta = await _responde(
        reproductor,
        _mensajes(CONSULTA_1, PIDE_ANALISIS, _devuelve("analyze_headline", movido)),
    )

    assert respuesta["content"] == NARRACION_1


# ----- Lo que no reproduce -----


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cambio",
    [
        {"probability": 0.953},
        {"probability": 0.949},
        {"verdict": "factual"},
        {"decided": 1},
        {"decided": False},
    ],
    ids=["+0,002", "-0,002", "otro-veredicto", "booleano-como-cifra", "otro-booleano"],
)
async def test_con_un_resultado_distinto_del_grabado_no_lo_narra(reproductor, cambio):
    """R13.4: contaría un resultado que no es el que se ve en las tarjetas.

    Un test de una salida pública afirma lo que NO está en ella (#185): la
    narración grabada no aparece, ni entera ni en parte."""
    distinto = {**ANALISIS, **cambio}

    respuesta = await _responde(
        reproductor,
        _mensajes(CONSULTA_1, PIDE_ANALISIS, _devuelve("analyze_headline", distinto)),
    )

    assert respuesta["content"] == HA_CAMBIADO.format(fecha="13 de noviembre de 2026")
    assert "0,951" not in respuesta["content"]
    assert respuesta["tool_calls"] == []
    assert respuesta["metrics"]["output_tokens"] is None


@pytest.mark.asyncio
async def test_con_el_resultado_de_otra_herramienta_no_lo_narra(reproductor):
    respuesta = await _responde(
        reproductor,
        _mensajes(
            CONSULTA_1, PIDE_ANALISIS, _devuelve("detect_clickbait_lexical", ANALISIS)
        ),
    )

    assert NARRACION_1 not in respuesta["content"]


@pytest.mark.asyncio
async def test_con_un_resultado_de_mas_no_lo_narra(reproductor):
    respuesta = await _responde(
        reproductor,
        _mensajes(
            CONSULTA_1,
            PIDE_ANALISIS,
            _devuelve("analyze_headline", ANALISIS),
            _devuelve("analyze_headline", ANALISIS),
        ),
    )

    assert NARRACION_1 not in respuesta["content"]


@pytest.mark.asyncio
async def test_con_otro_prompt_no_reproduce_nada(reproductor):
    """La grabación es lo que escribió el modelo con UNAS instrucciones: con
    otras, no se puede decir que hubiera escrito lo mismo."""
    with capture_logs() as registrado:
        respuesta = await _responde(
            reproductor, _mensajes(CONSULTA_1, prompt="Otro prompt.")
        )

    assert respuesta["tool_calls"] == []
    assert respuesta["content"].startswith("Lo que recibe el modelo ha cambiado")
    (evento,) = [
        linea for linea in registrado if linea["event"] == "grabado.ha_cambiado"
    ]
    assert evento["motivo"] == "prompt"


@pytest.mark.asyncio
async def test_si_pide_mas_vueltas_de_las_grabadas_no_inventa_ninguna(reproductor):
    respuesta = await _responde(
        reproductor,
        _mensajes(
            CONSULTA_1,
            PIDE_ANALISIS,
            _devuelve("analyze_headline", ANALISIS),
            {"role": "assistant", "content": NARRACION_1},
            {"role": "system", "content": PEDIR_RESPUESTA},
        ),
    )

    assert respuesta["content"].startswith("Lo que recibe el modelo ha cambiado")


@pytest.mark.asyncio
async def test_una_consulta_no_grabada_dice_cuales_lo_estan(reproductor):
    respuesta = await _responde(reproductor, _mensajes("¿Qué tiempo hace en Madrid?"))

    assert respuesta["tool_calls"] == []
    assert "no está entre las grabadas" in respuesta["content"]
    assert f"«{CONSULTA_1}»" in respuesta["content"]
    assert f"«{CONSULTA_2}»" in respuesta["content"]
    assert respuesta["metrics"] == {
        "prompt_tokens": None,
        "output_tokens": None,
        "load_s": 0.0,
        "total_s": 0.0,
    }


# ----- Disponibilidad, ficha y lo que se publica -----


@pytest.mark.asyncio
async def test_esta_disponible_y_dice_que_son_respuestas_grabadas(reproductor):
    disponibilidad = await reproductor.disponibilidad()

    assert disponibilidad.status == "available"
    assert disponibilidad.model == "qwen3.5:27b"
    assert "13 de noviembre de 2026" in disponibilidad.detail
    assert "consultas grabadas" in disponibilidad.detail


def test_publica_el_modelo_la_fecha_y_el_commit(reproductor):
    informacion = reproductor.info()

    assert informacion is not None
    assert informacion["model"] == "qwen3.5:27b"
    assert informacion["recorded_at"].isoformat() == "2026-11-13"
    assert informacion["commit"] == "abc1234"


def test_la_ficha_es_opaca_y_dice_de_donde_sale(reproductor):
    ficha = reproductor.ficha()

    assert ficha["type"] == "opaque"
    assert ficha["model_id"] == "qwen3.5:27b"
    assert ficha["name"] == "Respuestas grabadas de qwen3.5:27b"
    limitaciones = " ".join(ficha["limitations"])
    for dato in ("`abc1234`", "`06-dato`", "13 de noviembre de 2026", "la 2.ª"):
        assert dato in limitaciones
    # Se lee en castellano: el margen, con coma decimal.
    assert "±0,001" in limitaciones
    assert "0.001" not in limitaciones
    assert f"«{CONSULTA_2}»" in limitaciones


@pytest.mark.asyncio
async def test_sin_el_fichero_lo_dice_y_no_lanza(tmp_path):
    reproductor = ReproductorGrabado(tmp_path / "no-existe.json")

    with capture_logs() as registrado:
        resultado = await reproductor.chat(_mensajes(CONSULTA_1), [])
        disponibilidad = await reproductor.disponibilidad()

    assert not resultado.success
    assert resultado.error == SIN_GRABACION
    assert disponibilidad.status == "model_missing"
    assert reproductor.info() is None
    assert reproductor.ficha()["limitations"] == [SIN_GRABACION]
    # Se lee una sola vez, y el motivo va al registro.
    assert [linea["event"] for linea in registrado].count("grabado.ilegible") == 1


@pytest.mark.asyncio
async def test_un_fichero_mal_formado_no_publica_el_error_del_validador(tmp_path):
    """El texto de una excepción de librería no va a una salida pública (#163):
    el `detail` lo enseña la pantalla."""
    ruta = tmp_path / "rota.json"
    ruta.write_text(json.dumps({"model": "qwen3.5:27b"}), encoding="utf-8")
    reproductor = ReproductorGrabado(ruta)

    with capture_logs() as registrado:
        disponibilidad = await reproductor.disponibilidad()

    assert disponibilidad.status == "model_missing"
    assert disponibilidad.detail == SIN_GRABACION
    assert "Field required" not in disponibilidad.detail
    (evento,) = [linea for linea in registrado if linea["event"] == "grabado.ilegible"]
    assert evento["tipo"] == "ValidationError"
    assert "Field required" in evento["detalle"]
