"""Tests del agente (#188), con un modelo guionizado y un MCP de verdad.

El modelo es falso —responde lo que dice el guion, vuelta a vuelta, y apunta lo
que recibe—, porque lo que se prueba es el bucle y no el modelo: contra la A40
se prueba aparte, con un guion de `spikes/`.

El MCP, en cambio, es real: un FastMCP diminuto con dos herramientas, servido
por `ASGITransport` como en `tests/api/test_catalog.py`. El protocolo se habla
entero —saludo, catálogo y llamada— sin abrir puertos, así que se prueba
también que el agente usa bien `core/mcp/`.

**El servidor se abre dentro de cada test**, con un gestor de contexto y no con
una fixture asíncrona: el *lifespan* abre un ámbito de cancelación de anyio que
tiene que cerrarse en la misma tarea que lo abrió (ver `test_catalog.py`).
"""

import copy
import dataclasses
import json
from contextlib import asynccontextmanager
from typing import TypedDict

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.exceptions import McpError
from structlog.testing import capture_logs

from backend.agent.agente import (
    AVISO_HISTORIAL,
    MAX_VUELTAS,
    RESULTADO_DE_OTRO_TURNO,
    SIN_HERRAMIENTAS,
    Configuracion,
    responder,
)
from backend.agent.traza import PasoHerramienta, Resultado, Turno
from backend.core.mcp import session as mcp_session
from backend.core.mcp import tools as mcp_tools
from backend.core.models import ToolResult
from backend.integrations.llm.base import (
    Disponibilidad,
    Herramienta,
    LLMBackend,
    Mensaje,
)

# El Host lleva puerto: la protección anti DNS-rebinding de FastMCP acepta
# `127.0.0.1:*` y rechazaría con 421 un Host sin él.
_BASE = "http://127.0.0.1:8765"
_URL = f"{_BASE}/mcp"
# Una ruta en la que no hay ningún servidor MCP: el saludo falla al instante.
_CAIDO = f"{_BASE}/aqui-no-hay-nada"

MEDIDAS = {"prompt_tokens": 2900, "output_tokens": 15, "load_s": 0.0, "total_s": 1.5}


class Eco(TypedDict):
    texto: str
    longitud: int


class Cifras(TypedDict):
    """Números con todos sus decimales, como los devuelven las señales de verdad."""

    probability: float
    similarity: float
    low: float
    tiny: float
    exact: float
    zero: float
    top_cues: list[tuple[str, float]]
    score: int
    headline: str


CIFRAS: Cifras = {
    "probability": 0.999997361581358,
    "similarity": 0.22802437841892242,
    "low": 0.0028548036503576396,
    "tiny": 0.00004,
    "exact": 1.0,
    "zero": 0.0,
    "top_cues": [("you", 5.619727385247914), ("question", -4.22095859934778)],
    "score": 4,
    "headline": "0.123456789 Ways To Read A Number",
}


def _servidor() -> FastMCP:
    """Un servidor MCP con una herramienta que responde, otra que falla y otra
    que devuelve cifras con todos sus decimales."""
    mcp = FastMCP("servidor-de-prueba")

    @mcp.tool()
    def eco(texto: str) -> Eco:
        """Devuelve el texto recibido y su longitud.

        Sirve para probar el bucle sin depender de ninguna señal.
        """
        return {"texto": texto, "longitud": len(texto)}

    @mcp.tool()
    def rota(texto: str) -> Eco:
        """Falla siempre, con un mensaje ya redactado para publicarse."""
        raise ToolError("La herramienta de prueba ha fallado a propósito.")

    @mcp.tool()
    def cifras() -> Cifras:
        """Devuelve cifras con todos sus decimales."""
        return CIFRAS

    return mcp


@asynccontextmanager
async def mcp_en_proceso(monkeypatch):
    """Hace que `core/mcp/` hable con el servidor de prueba sin salir del proceso."""
    app = _servidor().streamable_http_app()

    # El gestor de sesiones de FastMCP arranca en el lifespan de la app, y
    # ASGITransport no lo ejecuta: hay que entrarlo a mano.
    async with app.router.lifespan_context(app):
        monkeypatch.setattr(
            mcp_session,
            "_http_client",
            lambda _timeout: httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=_BASE
            ),
        )
        yield


class ModeloGuionado(LLMBackend):
    """Un modelo que responde lo que dice el guion y apunta lo que recibe."""

    def __init__(self, *respuestas: ToolResult) -> None:
        self.respuestas = list(respuestas)
        self.conversaciones: list[list[Mensaje]] = []
        self.catalogos: list[list[Herramienta]] = []
        self.razonar: list[bool] = []

    async def chat(
        self,
        messages: list[Mensaje],
        tools: list[Herramienta],
        *,
        think: bool = False,
    ) -> ToolResult:
        # Una copia: el agente sigue añadiendo mensajes a la misma lista.
        self.conversaciones.append(copy.deepcopy(messages))
        self.catalogos.append(tools)
        self.razonar.append(think)
        return self.respuestas.pop(0)

    async def disponibilidad(self) -> Disponibilidad:
        return Disponibilidad("available", "El asistente está disponible.")


def _pide(*llamadas: tuple[str, dict], texto: str = "") -> ToolResult:
    """Una vuelta en la que el modelo pide herramientas."""
    return ToolResult.ok(
        {
            "content": texto,
            "tool_calls": [
                {"name": nombre, "arguments": argumentos}
                for nombre, argumentos in llamadas
            ],
            "metrics": MEDIDAS,
        }
    )


def _responde(texto: str) -> ToolResult:
    """Una vuelta en la que el modelo contesta sin pedir nada."""
    return ToolResult.ok({"content": texto, "tool_calls": [], "metrics": MEDIDAS})


def _config(modelo: LLMBackend, **cambios) -> Configuracion:
    base = Configuracion(
        backend=modelo,
        servers=[_URL],
        prompt="Eres un asistente de prueba.",
        discovery_timeout=5.0,
        execute_timeout=5.0,
    )
    return dataclasses.replace(base, **cambios)


def _herramientas(resultado: Resultado) -> list[PasoHerramienta]:
    """Sólo los pasos de herramienta de la traza, en orden."""
    return [paso for paso in resultado["steps"] if paso["kind"] == "tool"]


# ----- El bucle -----


@pytest.mark.asyncio
async def test_pide_una_herramienta_y_responde_con_su_resultado(monkeypatch):
    modelo = ModeloGuionado(
        _pide(("eco", {"texto": "hola"})), _responde("El eco dice hola.")
    )

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Repite hola", [], _config(modelo))

    assert resultado["status"] == "answered"
    assert resultado["answer"] == "El eco dice hola."
    assert resultado["rounds"] == 2
    assert [paso["kind"] for paso in resultado["steps"]] == ["model", "tool", "model"]

    (paso,) = _herramientas(resultado)
    assert paso["name"] == "eco"
    assert paso["arguments"] == {"texto": "hola"}
    assert paso["status"] == "ok"
    assert paso["data"] == {"texto": "hola", "longitud": 4}
    assert paso["error"] is None
    # El nombre que declara el propio servidor, no la URL de la configuración.
    assert paso["server"] == "servidor-de-prueba"


@pytest.mark.asyncio
async def test_el_resultado_vuelve_al_modelo_como_mensaje_de_herramienta(monkeypatch):
    modelo = ModeloGuionado(_pide(("eco", {"texto": "hola"})), _responde("Hecho."))

    async with mcp_en_proceso(monkeypatch):
        await responder("Repite hola", [], _config(modelo))

    *_, peticion, devuelto = modelo.conversaciones[1]
    # Su propia petición va antes, para que sepa en la vuelta siguiente qué pidió.
    assert peticion == {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"name": "eco", "arguments": {"texto": "hola"}}],
    }
    assert devuelto["role"] == "tool"
    assert devuelto.get("tool_name") == "eco"
    assert json.loads(devuelto["content"]) == {"texto": "hola", "longitud": 4}


@pytest.mark.asyncio
async def test_el_catalogo_llega_al_modelo_con_su_esquema(monkeypatch):
    modelo = ModeloGuionado(_responde("No hace falta ninguna herramienta."))

    async with mcp_en_proceso(monkeypatch):
        await responder("Hola", [], _config(modelo))

    catalogo = {herramienta["name"]: herramienta for herramienta in modelo.catalogos[0]}
    assert set(catalogo) == {"eco", "rota", "cifras"}
    # Sin la sangría del docstring, que FastMCP manda tal cual y el modelo
    # pagaría en cada petición.
    assert catalogo["eco"]["description"] == (
        "Devuelve el texto recibido y su longitud.\n\n"
        "Sirve para probar el bucle sin depender de ninguna señal."
    )
    assert "texto" in catalogo["eco"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_el_modelo_razona_por_defecto(monkeypatch):
    """Sin razonar, el 27B se inventó el resultado de las herramientas sin
    llamarlas (A40, 2026-09-26): el agente lo pide siempre, sin depender del
    defecto de Ollama."""
    modelo = ModeloGuionado(_pide(("eco", {"texto": "hola"})), _responde("Hecho."))

    async with mcp_en_proceso(monkeypatch):
        await responder("Repite hola", [], _config(modelo))

    assert modelo.razonar == [True, True]


@pytest.mark.asyncio
async def test_el_historial_va_entre_el_prompt_y_la_consulta(monkeypatch):
    modelo = ModeloGuionado(_responde("El lineal no se ha consultado todavía."))
    historial: list[Turno] = [
        {"role": "user", "content": "¿Es clickbait este titular?"},
        {"role": "assistant", "content": "El detector léxico no encontró pistas."},
    ]

    async with mcp_en_proceso(monkeypatch):
        await responder("¿Y el lineal?", historial, _config(modelo))

    assert modelo.conversaciones[0] == [
        {"role": "system", "content": "Eres un asistente de prueba."},
        *historial,
        {"role": "system", "content": AVISO_HISTORIAL},
        {"role": "user", "content": "¿Y el lineal?"},
    ]


@pytest.mark.asyncio
async def test_sin_historial_no_hay_aviso(monkeypatch):
    """El aviso sólo tiene sentido si hay turnos que imitar: sin ellos, la
    conversación es la misma que se midió en la comparación de #192."""
    modelo = ModeloGuionado(_responde("Hola."))

    async with mcp_en_proceso(monkeypatch):
        await responder("Hola", [], _config(modelo))

    assert modelo.conversaciones[0] == [
        {"role": "system", "content": "Eres un asistente de prueba."},
        {"role": "user", "content": "Hola"},
    ]


@pytest.mark.asyncio
async def test_el_aviso_del_historial_se_puede_quitar(monkeypatch):
    """`None` lo desactiva, para medir con y sin (#192)."""
    modelo = ModeloGuionado(_responde("Hola."))
    historial: list[Turno] = [
        {"role": "user", "content": "¿Es clickbait este titular?"},
        {"role": "assistant", "content": "No."},
    ]

    async with mcp_en_proceso(monkeypatch):
        await responder(
            "¿Y este otro?", historial, _config(modelo, aviso_historial=None)
        )

    assert [mensaje["role"] for mensaje in modelo.conversaciones[0]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]


@pytest.mark.asyncio
async def test_las_herramientas_de_un_turno_anterior_van_delante_de_su_respuesta(
    monkeypatch,
):
    """#192: con sólo el texto, el modelo veía respuestas con veredictos y
    ninguna llamada delante, y las imitaba sin llamar a nada. Van los nombres,
    con un resultado que dice que ya no está: la forma que tuvo el turno."""
    modelo = ModeloGuionado(_responde("Hola."))
    historial: list[Turno] = [
        {"role": "user", "content": "¿Es clickbait este titular?"},
        {"role": "assistant", "content": "No lo es.", "tools": ["eco", "cifras"]},
    ]

    async with mcp_en_proceso(monkeypatch):
        await responder(
            "¿Y este otro?", historial, _config(modelo, aviso_historial=None)
        )

    assert modelo.conversaciones[0] == [
        {"role": "system", "content": "Eres un asistente de prueba."},
        {"role": "user", "content": "¿Es clickbait este titular?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"name": "eco", "arguments": {}},
                {"name": "cifras", "arguments": {}},
            ],
        },
        {"role": "tool", "tool_name": "eco", "content": RESULTADO_DE_OTRO_TURNO},
        {"role": "tool", "tool_name": "cifras", "content": RESULTADO_DE_OTRO_TURNO},
        {"role": "assistant", "content": "No lo es."},
        {"role": "user", "content": "¿Y este otro?"},
    ]


@pytest.mark.asyncio
async def test_cada_paso_se_avisa_segun_ocurre(monkeypatch):
    """El aviso de una herramienta llega ANTES de la vuelta siguiente del modelo.

    Es lo que dejará a la API enseñar la traza mientras crece, en vez de al
    final (§12 de `docs/arquitectura.md`).
    """
    modelo = ModeloGuionado(_pide(("eco", {"texto": "hola"})), _responde("Hecho."))
    avisos = []

    def al_paso(paso):
        avisos.append((paso["kind"], len(modelo.conversaciones)))

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Repite hola", [], _config(modelo), al_paso)

    assert avisos == [("model", 1), ("tool", 1), ("model", 2)]
    assert len(avisos) == len(resultado["steps"])


@pytest.mark.asyncio
async def test_la_traza_guarda_el_resultado_entero_aunque_el_modelo_lo_lea_recortado(
    monkeypatch,
):
    largo = "x" * 500
    modelo = ModeloGuionado(_pide(("eco", {"texto": largo})), _responde("Hecho."))

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Repite", [], _config(modelo, max_result_chars=100))

    (paso,) = _herramientas(resultado)
    assert paso["data"] == {"texto": largo, "longitud": 500}

    leido = modelo.conversaciones[1][-1]["content"]
    assert len(leido) < 200
    # El recorte se dice: un JSON cortado sin aviso invita a completarlo de memoria.
    assert "recortado" in leido


@pytest.mark.asyncio
async def test_el_modelo_lee_las_cifras_con_tres_decimales_y_la_traza_enteras(
    monkeypatch,
):
    """El modelo copiaba los decimales enteros («0,9996088089831324») aunque el
    prompt no se lo pidiera, y eso hacía la respuesta ilegible (#191, #192).
    Pedirle que redondee no lo garantiza; si no los lee, no los puede copiar.
    Las tarjetas salen de la traza, que los conserva (R13.4)."""
    modelo = ModeloGuionado(_pide(("cifras", {})), _responde("Hecho."))

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Dame las cifras", [], _config(modelo))

    (paso,) = _herramientas(resultado)
    assert paso["data"] == json.loads(json.dumps(CIFRAS))

    leido = json.loads(modelo.conversaciones[1][-1]["content"])
    assert leido["similarity"] == 0.228
    assert leido["low"] == 0.003
    assert leido["top_cues"] == [["you", 5.62], ["question", -4.221]]
    # Lo que no es un decimal no se toca: ni los enteros ni el texto.
    assert leido["score"] == 4
    assert leido["headline"] == "0.123456789 Ways To Read A Number"


@pytest.mark.asyncio
async def test_lo_que_no_es_cero_ni_uno_no_se_redondea_a_cero_ni_a_uno(monkeypatch):
    """0,9999973 con tres decimales es 1, y el modelo diría «probabilidad de 1»:
    una certeza que la herramienta no dio. Se queda en 0,999, y lo casi nulo en
    0,001. Lo que sí es exactamente 0 o 1 se deja."""
    modelo = ModeloGuionado(_pide(("cifras", {})), _responde("Hecho."))

    async with mcp_en_proceso(monkeypatch):
        await responder("Dame las cifras", [], _config(modelo))

    leido = json.loads(modelo.conversaciones[1][-1]["content"])
    assert leido["probability"] == 0.999
    assert leido["tiny"] == 0.001
    assert leido["exact"] == 1.0
    assert leido["zero"] == 0.0


@pytest.mark.asyncio
async def test_sin_redondeo_el_modelo_lee_las_cifras_enteras(monkeypatch):
    """`None` lo desactiva, para poder medir con y sin (#192)."""
    modelo = ModeloGuionado(_pide(("cifras", {})), _responde("Hecho."))

    async with mcp_en_proceso(monkeypatch):
        await responder(
            "Dame las cifras", [], _config(modelo, decimales_para_el_modelo=None)
        )

    leido = json.loads(modelo.conversaciones[1][-1]["content"])
    assert leido == json.loads(json.dumps(CIFRAS))


# ----- Cómo termina -----


@pytest.mark.asyncio
async def test_se_detiene_al_agotar_las_vueltas(monkeypatch):
    modelo = ModeloGuionado(*[_pide(("eco", {"texto": "otra vez"}))] * MAX_VUELTAS)

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Prueba", [], _config(modelo))

    assert MAX_VUELTAS == 6  # el tope del spike #82
    assert resultado["status"] == "max_rounds"
    assert resultado["rounds"] == MAX_VUELTAS
    assert len(modelo.conversaciones) == MAX_VUELTAS
    assert resultado["answer"] == ""
    # La traza se conserva entera: las tarjetas salen igual (R6.13).
    assert len(_herramientas(resultado)) == MAX_VUELTAS


@pytest.mark.asyncio
async def test_una_narracion_vacia_no_es_una_respuesta(monkeypatch):
    """El modo de fallo del spike #82: pide bien las herramientas y no escribe nada."""
    modelo = ModeloGuionado(_pide(("eco", {"texto": "hola"})), _responde("  \n"))

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Repite hola", [], _config(modelo))

    assert resultado["status"] == "empty_answer"
    assert resultado["answer"] == ""
    (paso,) = _herramientas(resultado)
    assert paso["data"] == {"texto": "hola", "longitud": 4}


@pytest.mark.asyncio
async def test_un_fallo_del_modelo_termina_con_su_mensaje(monkeypatch):
    fallo = "El modelo `qwen3.5:27b` tardó demasiado en responder."
    modelo = ModeloGuionado(ToolResult.fail(fallo))

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Hola", [], _config(modelo))

    assert resultado["status"] == "failed"
    assert resultado["detail"] == fallo
    assert resultado["steps"] == []


# ----- Los errores de una herramienta vuelven al modelo -----


@pytest.mark.asyncio
async def test_el_error_de_una_herramienta_vuelve_al_modelo(monkeypatch):
    modelo = ModeloGuionado(
        _pide(("rota", {"texto": "hola"})), _responde("La herramienta falló.")
    )

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Prueba", [], _config(modelo))

    (paso,) = _herramientas(resultado)
    assert paso["status"] == "error"
    # El motivo, entero y sin el «Error executing tool rota: » que antepone
    # FastMCP: se quita donde se lee el error (#191).
    assert paso["error"] == "La herramienta de prueba ha fallado a propósito."
    assert paso["data"] is None
    assert json.loads(modelo.conversaciones[1][-1]["content"]) == {
        "error": paso["error"]
    }
    # El bucle sigue: el modelo puede contarlo o corregirse.
    assert resultado["status"] == "answered"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("llamada", "fragmento"),
    [
        (("inventada", {}), "No hay ninguna herramienta llamada «inventada»"),
        (("eco", {"texto": 3}), "Los argumentos no encajan en el esquema de «eco»"),
        (("eco", {}), "Los argumentos no encajan en el esquema de «eco»"),
    ],
    ids=["no-existe", "tipo-equivocado", "falta-un-argumento"],
)
async def test_una_llamada_mal_hecha_vuelve_al_modelo_para_que_la_corrija(
    monkeypatch, llamada, fragmento
):
    modelo = ModeloGuionado(
        _pide(llamada), _pide(("eco", {"texto": "hola"})), _responde("Hecho.")
    )

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Prueba", [], _config(modelo))

    fallida, corregida = _herramientas(resultado)
    assert fallida["status"] == "error"
    assert fragmento in (fallida["error"] or "")
    assert corregida["status"] == "ok"
    assert resultado["status"] == "answered"


@pytest.mark.asyncio
async def test_una_herramienta_que_tarda_demasiado_vuelve_al_modelo(monkeypatch):
    async def se_agota(name, arguments, *, servers, timeout):
        raise mcp_tools.ToolTimeout(name)

    modelo = ModeloGuionado(_pide(("eco", {"texto": "hola"})), _responde("Tardó."))

    async with mcp_en_proceso(monkeypatch):
        monkeypatch.setattr(mcp_tools, "execute_tool", se_agota)
        resultado = await responder("Prueba", [], _config(modelo))

    (paso,) = _herramientas(resultado)
    assert paso["error"] == "«eco» tardó demasiado en responder."


@pytest.mark.asyncio
async def test_un_fallo_imprevisto_se_registra_entero_y_no_se_publica(monkeypatch):
    """La traza y lo que lee el modelo son salidas públicas (#163, #89).

    Un test de una salida pública afirma lo que NO está en ella (#185), y que el
    log sí lo conserva: sanear sin registrar ciega la depuración.
    """

    async def revienta(name, arguments, *, servers, timeout):
        raise RuntimeError("detalle interno en /app/backend/algo.py")

    modelo = ModeloGuionado(_pide(("eco", {"texto": "hola"})), _responde("Falló."))

    async with mcp_en_proceso(monkeypatch):
        monkeypatch.setattr(mcp_tools, "execute_tool", revienta)
        with capture_logs() as registrado:
            resultado = await responder("Prueba", [], _config(modelo))

    publicado = json.dumps(resultado, ensure_ascii=False) + json.dumps(
        modelo.conversaciones, ensure_ascii=False
    )
    assert "detalle interno" not in publicado
    assert "RuntimeError" not in publicado
    (paso,) = _herramientas(resultado)
    assert "motivo no previsto" in (paso["error"] or "")

    (evento,) = [
        linea
        for linea in registrado
        if linea["event"] == "agent.herramienta.imprevisto"
    ]
    assert "detalle interno" in evento["detalle"]
    assert "RuntimeError" in evento["traza"]


# ----- El catálogo -----


@pytest.mark.asyncio
async def test_un_servidor_caido_no_tumba_el_catalogo(monkeypatch):
    modelo = ModeloGuionado(_pide(("eco", {"texto": "hola"})), _responde("Hecho."))

    async with mcp_en_proceso(monkeypatch):
        with capture_logs() as registrado:
            resultado = await responder(
                "Prueba", [], _config(modelo, servers=[_CAIDO, _URL])
            )

    assert resultado["status"] == "answered"
    (paso,) = _herramientas(resultado)
    assert paso["status"] == "ok"
    assert any(linea["event"] == "agent.servidor_inalcanzable" for linea in registrado)


@pytest.mark.asyncio
async def test_por_que_cada_herramienta_se_ejecuta_solo_en_su_servidor(monkeypatch):
    """`execute_tool` recorre los servidores en orden, y uno caído delante lo
    hace fallar antes de llegar al que tiene la herramienta. Por eso el agente
    le pasa sólo la URL del servidor que la publicó."""
    async with mcp_en_proceso(monkeypatch):
        with pytest.raises(ExceptionGroup) as fallo:
            await mcp_tools.execute_tool(
                "eco", {"texto": "hola"}, servers=[_CAIDO, _URL], timeout=5.0
            )

    # Dos grupos, uno por cada task group de anyio, con el fallo del saludo
    # dentro: el servidor bueno ni se llega a consultar.
    assert fallo.group_contains(McpError, depth=None)


@pytest.mark.asyncio
async def test_sin_ninguna_herramienta_no_se_llama_al_modelo(monkeypatch):
    modelo = ModeloGuionado()

    async with mcp_en_proceso(monkeypatch):
        resultado = await responder("Prueba", [], _config(modelo, servers=[_CAIDO]))

    assert resultado["status"] == "failed"
    assert resultado["detail"] == SIN_HERRAMIENTAS
    assert modelo.conversaciones == []
