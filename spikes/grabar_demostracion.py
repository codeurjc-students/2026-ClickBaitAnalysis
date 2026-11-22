"""#265 (2026-11-13) - Graba las respuestas del asistente para la demostración.

El plan B de la defensa (`docs/demostracion.md`): si la máquina 2 no se puede
usar, la API reproduce lo que escribió el modelo al grabar la conversación del
paso 6, y las herramientas se ejecutan de verdad
(`backend/integrations/llm/grabado.py`). Este guion la graba.

Cómo:

- Las tres preguntas se leen de `docs/demostracion.md` («Las tres preguntas del
  paso 6»), para que la guía y la grabación no puedan decir cosas distintas.
- El agente REAL (`responder`), con el `mcp` de `backend.main` servido en
  proceso y la configuración de producción —los valores por defecto de
  `Settings`: `06-dato`, `num_ctx`, el muestreo, el tope de salida,
  razonando—, como `agente_inyeccion.py`. Sólo cambian el servidor de Ollama y
  el modelo.
- Entre el agente y Ollama, una `Grabadora` que apunta cada vuelta: lo que
  respondió el modelo —texto, herramientas con sus argumentos, medidas y si
  salió cortada— y los resultados que LEYÓ antes de darla, tal como se los
  pasó el agente, con las cifras redondeadas. Es lo que compara el
  reproductor.
- Los turnos 2 y 3 llevan el historial que mandaría la pantalla
  (`historialQueCabe`, en `frontend/src/app/asistente/conversacion.ts`): la
  pregunta y la respuesta de cada turno anterior, con los nombres de sus
  herramientas, quitando los más antiguos si pasan del tope.
- Tres tomas (`GRABACION_TOMAS`), y la regla publicada en #265 antes de grabar
  decide cuál se queda. El guion comprueba las condiciones 1 y 2 —la
  herramienta esperada en cada turno, y que todos acaben con respuesta—; la 3,
  que cada narración sea fiel a su traza, la juzga el autor leyéndolas. Si en
  ninguna toma el turno 2 llama a `detect_clickbait_linear`, se graba también
  la conversación con cada redacción de repuesto (`REPUESTOS_TURNO_2`).
- Antes de llamar al modelo comprueba que los modelos de las señales en la
  caché son los de sus fichas, y los carga sin red, como
  `ejemplos_formulario.py` (#282): la grabación se reproduce donde la imagen
  los lleva horneados, y con otros, sus resultados no cuadrarían allí. La
  grabación con el 2B del 13 nov se hizo con red; la caché seguía en las
  revisiones de las fichas después, y en la imagen se reprodujo entera.

Ejecutar desde la raíz. Primero sin modelo, que no gasta ninguna sesión:

    CUDA_VISIBLE_DEVICES= .venv/bin/python spikes/grabar_demostracion.py --en-seco

Con el 2B en la GTX, para probar el mecanismo (un Ollama en el 11435 con
`OLLAMA_MODELS=/mnt/b/ollama-models`, como en #260):

    CUDA_VISIBLE_DEVICES= OLLAMA_URL=http://127.0.0.1:11435 OLLAMA_MODELO=qwen3.5:2b \\
        .venv/bin/python spikes/grabar_demostracion.py <carpeta>

Con el 27B de la A40, la sesión la abre `spikes/agente_a40.sh`:

    AGENTE_A40_GUION=spikes/grabar_demostracion.py CUDA_VISIBLE_DEVICES= \\
        OLLAMA_URL=http://127.0.0.1:11500 OLLAMA_MODELO=qwen3.5:27b \\
        setsid nohup bash spikes/agente_a40.sh <carpeta> \\
        > /tmp/grabacion.log 2>&1 < /dev/null & disown

`CUDA_VISIBLE_DEVICES=` deja las señales en CPU, como en producción. Escribe
`<carpeta>/tomas.json` y se niega a pisarlo. Leídas las tomas, la elegida pasa
a `backend/integrations/llm/grabaciones/<nombre>.json` (por defecto,
`demostracion`, la que reproduce `compose.grabado.yaml`):

    .venv/bin/python spikes/grabar_demostracion.py --elegir <carpeta>/tomas.json <toma> [nombre]

Y se comprueba que se reproduce entera, sin modelo: las consultas grabadas
pasan por el agente con el reproductor y las herramientas de verdad, como en la
API con `compose.grabado.yaml`, y el guion termina con error si algún turno no
reproduce lo grabado. Sirve también la víspera de la defensa:

    CUDA_VISIBLE_DEVICES= .venv/bin/python spikes/grabar_demostracion.py --reproducir [nombre]

Lo mismo por la API de un despliegue encendido con `compose.grabado.yaml`,
como lo haría la pantalla —`POST /chat` con el historial y `GET /chat/{id}`
hasta que termina—, comparando cada vuelta del modelo de la traza con la
grabada. Comprueba antes, en `GET /agent`, que sirve la misma grabación que la
de aquí. En la pila local (con el certificado de Caddy, que no se verifica en
`localhost`) o en la máquina 1:

    .venv/bin/python spikes/grabar_demostracion.py --reproducir-en https://localhost/api [nombre]
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import structlog
from pydantic import TypeAdapter

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Sin red para Hugging Face, como `ejemplos_formulario.py` (#282):
# `LocalNLPClient` pide cada modelo por su nombre, sin revisión, y con red
# cargaría lo que hubiera ese día en el Hub. Sin ella carga el `refs/main` de la
# caché, que es lo que `comprobar_revisiones` coteja con las fichas. Antes de
# importar nada que lea la variable. Ollama no pasa por aquí.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from backend.agent import prompts  # noqa: E402
from backend.agent.agente import Configuracion, responder  # noqa: E402
from backend.agent.traza import Resultado, Turno  # noqa: E402
from backend.config.settings import Settings  # noqa: E402
from backend.core.idioma import ESPANOL, INGLES  # noqa: E402
from backend.core.mcp import session as mcp_session  # noqa: E402
from backend.core.models import ToolResult  # noqa: E402
from backend.integrations.llm.base import (  # noqa: E402
    Disponibilidad,
    Herramienta,
    LLMBackend,
    Mensaje,
)
from backend.integrations.llm.grabado import (  # noqa: E402
    CARPETA,
    Grabacion,
    ReproductorGrabado,
)
from backend.integrations.llm.ollama import OllamaClient  # noqa: E402
from backend.integrations.nlp.model_cards import fichas_en  # noqa: E402
from backend.main import mcp as SERVIDOR  # noqa: E402

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
)
for ruidoso in ("httpx", "mcp", "backend"):
    logging.getLogger(ruidoso).setLevel(logging.WARNING)

URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")
MODELO = os.environ.get("OLLAMA_MODELO", "qwen3.5:2b")
TOMAS = int(os.environ.get("GRABACION_TOMAS", "3"))
_BASE = "http://127.0.0.1:8765"

GUIA = RAIZ / "docs" / "demostracion.md"
MARCA_DE_LAS_PREGUNTAS = "Las tres preguntas del paso 6:"

# La configuración de producción: los valores por defecto de `Settings`, que
# son los que no cambia el compose.
DEFECTO = {nombre: campo.default for nombre, campo in Settings.model_fields.items()}

# La herramienta que espera cada turno, según la tabla del paso 6 de la guía
# (condición 1 de la regla de #265). En el 3, el análisis o cualquier señal.
SENALES = {
    "analyze_headline",
    "detect_clickbait",
    "detect_clickbait_lexical",
    "detect_clickbait_linear",
    "detect_clickbait_incoherence",
    "analyze_sentiment",
}
ESPERADAS = [{"analyze_headline"}, {"detect_clickbait_linear"}, SENALES]

# Las redacciones de repuesto del turno 2: la pregunta de la guía no se ha
# probado nunca con el 27B y ese titular. Sólo se graban si en ninguna toma el
# turno 2 llama a `detect_clickbait_linear`, y se publican en #265 antes de
# abrir la sesión. `{titular}` es el de la pregunta de la guía.
REPUESTOS_TURNO_2 = (
    "¿Qué palabras de '{titular}' pesan más para que sea clickbait, y cuánto?",
    "Enséñame el peso de cada palabra de '{titular}' en el modelo entrenado en "
    "este proyecto.",
)


def preguntas_de_la_guia() -> list[str]:
    """Las tres preguntas del paso 6, tal cual están en la guía."""
    texto = GUIA.read_text(encoding="utf-8")
    if texto.count(MARCA_DE_LAS_PREGUNTAS) != 1:
        sys.exit(f"La guía no tiene una sola vez «{MARCA_DE_LAS_PREGUNTAS}».")
    despues = texto.split(MARCA_DE_LAS_PREGUNTAS, 1)[1]
    bloques = re.findall(r"```text\n(.*?)\n```", despues, re.DOTALL)[:3]
    if len(bloques) != 3 or any("\n" in bloque for bloque in bloques):
        sys.exit("Tras la marca no hay tres bloques `text` de una línea cada uno.")
    return bloques


def con_repuesto(preguntas: list[str], repuesto: str) -> list[str]:
    """Las preguntas de la guía, con el turno 2 cambiado por un repuesto."""
    titular = re.search(r"'(.+)'", preguntas[1])
    if titular is None:
        sys.exit("La pregunta del turno 2 no lleva el titular entre comillas simples.")
    return [preguntas[0], repuesto.format(titular=titular.group(1)), preguntas[2]]


def historial_que_cabe(
    intercambios: list[tuple[str, Resultado]], tope: int
) -> list[Turno]:
    """El historial que manda la pantalla con la pregunta siguiente.

    Es `historialQueCabe` del frontend: cada turno anterior con respuesta, con
    los nombres de las herramientas que usó, sin repetir y en orden; y si pasa
    de `tope` caracteres, se quitan las parejas más antiguas. `len` cuenta
    caracteres y `length`, unidades UTF-16: sólo difieren con emojis.
    """
    parejas: list[list[Turno]] = []
    for pregunta, resultado in intercambios:
        respuesta = resultado["answer"].strip()
        if not respuesta:
            continue
        nombres = list(
            dict.fromkeys(
                paso["name"] for paso in resultado["steps"] if paso["kind"] == "tool"
            )
        )
        asistente: Turno = {"role": "assistant", "content": respuesta}
        if nombres:
            asistente["tools"] = nombres
        parejas.append([{"role": "user", "content": pregunta}, asistente])

    def medir(pareja: list[Turno]) -> int:
        return sum(
            len(turno["content"])
            + sum(len(nombre) for nombre in turno.get("tools", []))
            for turno in pareja
        )

    total = sum(medir(pareja) for pareja in parejas)
    while parejas and total > tope:
        total -= medir(parejas.pop(0))
    return [turno for pareja in parejas for turno in pareja]


class Grabadora(LLMBackend):
    """Envuelve al cliente de Ollama y apunta cada vuelta de un turno: lo que
    respondió el modelo y los resultados que leyó desde la vuelta anterior.

    Es el formato de `VueltaGrabada` en `grabado.py`. `vueltas` se vacía al
    empezar cada turno.
    """

    def __init__(self, backend: LLMBackend) -> None:
        self.backend = backend
        self.vueltas: list[dict] = []

    async def chat(
        self, messages: list[Mensaje], tools: list[Herramienta], *, think: bool = False
    ) -> ToolResult:
        posicion = max(
            indice
            for indice, mensaje in enumerate(messages)
            if mensaje["role"] == "user"
        )
        leidos = [
            {"tool_name": mensaje.get("tool_name", ""), "content": mensaje["content"]}
            for mensaje in messages[posicion + 1 :]
            if mensaje["role"] == "tool"
        ]
        ya_apuntados = sum(len(vuelta["tool_results"]) for vuelta in self.vueltas)

        resultado = await self.backend.chat(messages, tools, think=think)
        if resultado.success:
            self.vueltas.append(
                {"tool_results": leidos[ya_apuntados:], "response": resultado.unwrap()}
            )
        return resultado

    async def disponibilidad(self) -> Disponibilidad:
        return await self.backend.disponibilidad()


def comprobar_revisiones() -> list[dict]:
    """El id y la revisión de cada modelo con ficha, en inglés y en español.

    La de la caché es la que se carga aquí, y tiene que ser la de la ficha, que
    es la que lleva la imagen: si no, los resultados de las herramientas al
    reproducir no serían los grabados.
    """
    from huggingface_hub import constants

    modelos: dict[str, str] = {}
    for idioma in (INGLES, ESPANOL):
        for ficha in fichas_en(idioma).values():
            if ficha["model_id"] is None or ficha["model_id"] in modelos:
                continue
            referencia = (
                Path(constants.HF_HUB_CACHE)
                / ("models--" + ficha["model_id"].replace("/", "--"))
                / "refs"
                / "main"
            )
            try:
                en_cache = referencia.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                sys.exit(f"{ficha['model_id']} no está en la caché de Hugging Face.")
            if en_cache != ficha["revision"]:
                sys.exit(
                    f"{ficha['model_id']}: en la caché está {en_cache[:12]} y la ficha "
                    f"fija {str(ficha['revision'])[:12]}. Lo grabado no sería lo que se sirve."
                )
            modelos[ficha["model_id"]] = en_cache
    return [
        {"model_id": nombre, "revision": revision}
        for nombre, revision in modelos.items()
    ]


def configuracion(backend: LLMBackend) -> Configuracion:
    """Como la monta `api/chat.py`, con los valores por defecto de `Settings`.
    Los cortes de MCP son más largos: aquí las señales cargan en frío, en el
    mismo proceso."""
    return Configuracion(
        backend=backend,
        servers=[f"{_BASE}/mcp"],
        prompt=prompts.cargar(DEFECTO["llm_prompt"]),
        discovery_timeout=10.0,
        execute_timeout=120.0,
    )


def cliente_de_ollama() -> OllamaClient:
    return OllamaClient(
        URL,
        MODELO,
        num_ctx=DEFECTO["llm_num_ctx"],
        keep_alive=DEFECTO["llm_keep_alive"],
        timeout=DEFECTO["llm_timeout"],
        temperature=DEFECTO["llm_temperature"],
        presence_penalty=DEFECTO["llm_presence_penalty"],
        num_predict=DEFECTO["llm_num_predict"],
    )


async def conversacion(
    preguntas: list[str], grabadora: Grabadora, config: Configuracion
) -> list[dict]:
    """Una toma: las preguntas, una detrás de otra, con el historial de la pantalla."""
    intercambios: list[tuple[str, Resultado]] = []
    turnos = []
    for pregunta in preguntas:
        historial = historial_que_cabe(intercambios, DEFECTO["chat_max_history_chars"])
        grabadora.vueltas = []
        resultado = await responder(pregunta, historial, config)
        intercambios.append((pregunta, resultado))
        turnos.append(
            {
                "query": pregunta,
                "historial": historial,
                "rounds": grabadora.vueltas,
                "estado": resultado["status"],
                "respuesta": resultado["answer"],
                "detalle": resultado["detail"],
                "total_s": round(resultado["total_s"], 1),
                "herramientas": [
                    {
                        "name": paso["name"],
                        "arguments": paso["arguments"],
                        "status": paso["status"],
                    }
                    for paso in resultado["steps"]
                    if paso["kind"] == "tool"
                ],
            }
        )
    return turnos


def condiciones_automaticas(turnos: list[dict]) -> dict:
    """Las condiciones 1 y 2 de la regla de #265, turno a turno. La 3, que la
    narración sea fiel a su traza, la juzga el autor leyéndola."""
    por_turno = []
    for turno, esperadas in zip(turnos, ESPERADAS, strict=True):
        llamadas = {herramienta["name"] for herramienta in turno["herramientas"]}
        por_turno.append(
            {
                "llama_a_la_esperada": bool(llamadas & esperadas),
                "acaba_con_respuesta": turno["estado"] == "answered",
            }
        )
    return {
        "por_turno": por_turno,
        "cumple_1_y_2": all(
            turno["llama_a_la_esperada"] and turno["acaba_con_respuesta"]
            for turno in por_turno
        ),
    }


async def ollama() -> tuple[str, str]:
    """La versión del servidor y el id del modelo, si lo tiene; si no, no se graba."""
    async with httpx.AsyncClient(timeout=10) as cliente:
        version = (await cliente.get(f"{URL}/api/version")).json()["version"]
        modelos = (await cliente.get(f"{URL}/api/tags")).json()["models"]
    por_nombre = {modelo["name"]: modelo["digest"][:12] for modelo in modelos}
    if MODELO not in por_nombre:
        sys.exit(f"{URL} no tiene {MODELO} (tiene {sorted(por_nombre)}).")
    return version, por_nombre[MODELO]


def git(*argumentos: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(RAIZ), *argumentos],
        capture_output=True,
        text=True,
        check=False,
    )


def imprimir_toma(toma: dict) -> None:
    """Lo que hace falta para juzgar la condición 3: cada turno, con lo que
    llamó y lo que respondió."""
    condiciones = toma["condiciones"]
    print(f"\n== toma {toma['toma']}{' (repuesto)' if toma['repuesto'] else ''}")
    for numero, (turno, marca) in enumerate(
        zip(toma["turnos"], condiciones["por_turno"], strict=True), start=1
    ):
        llamadas = ", ".join(
            f"{herramienta['name']}({json.dumps(herramienta['arguments'], ensure_ascii=False)})"
            for herramienta in turno["herramientas"]
        )
        print(
            f"-- turno {numero}: {turno['estado']}, {turno['total_s']} s, "
            f"{len(turno['rounds'])} vueltas · esperada {marca['llama_a_la_esperada']}"
        )
        print(f"   pregunta: {turno['query']}")
        print(f"   llama a: {llamadas or '(nada)'}")
        print(f"   responde: {turno['respuesta'] or turno['detalle']}")
    print(f"-- condiciones 1 y 2: {condiciones['cumple_1_y_2']}")


async def grabar(carpeta: Path) -> None:
    salida = carpeta / "tomas.json"
    if salida.exists():
        sys.exit(f"{salida} ya existe: se pisaría una grabación.")
    preguntas = preguntas_de_la_guia()
    revisiones = comprobar_revisiones()
    version, digest = await ollama()
    await asyncio.to_thread(carpeta.mkdir, parents=True, exist_ok=True)

    registro: dict = {
        "condiciones": {
            "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
            "commit": git("rev-parse", "--short", "HEAD").stdout.strip(),
            "cambios_sin_commitear": git(
                "diff", "--quiet", "HEAD", "--", "backend"
            ).returncode
            != 0,
            "ollama": version,
            "servidor": URL,
            "modelo": MODELO,
            "digest": digest,
            "prompt": DEFECTO["llm_prompt"],
            "texto_del_prompt": prompts.cargar(DEFECTO["llm_prompt"]),
            "num_ctx": DEFECTO["llm_num_ctx"],
            "temperature": DEFECTO["llm_temperature"],
            "presence_penalty": DEFECTO["llm_presence_penalty"],
            "num_predict": DEFECTO["llm_num_predict"],
            "think": True,
            "tope_del_historial": DEFECTO["chat_max_history_chars"],
            "tomas_por_redaccion": TOMAS,
            "senales_en": "CPU"
            if os.environ.get("CUDA_VISIBLE_DEVICES") == ""
            else "sin fijar",
            "modelos_de_las_senales": revisiones,
        },
        "tomas": [],
    }
    print("== condiciones")
    for clave, valor in registro["condiciones"].items():
        if clave != "texto_del_prompt":
            print(f"  {clave}: {valor}")

    grabadora = Grabadora(cliente_de_ollama())
    config = configuracion(grabadora)
    app = SERVIDOR.streamable_http_app()
    async with app.router.lifespan_context(app):
        mcp_session._http_client = lambda corte: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE, timeout=corte
        )

        async def tomar(preguntas_de_la_toma: list[str], repuesto: bool) -> dict:
            turnos = await conversacion(preguntas_de_la_toma, grabadora, config)
            toma = {
                "toma": len(registro["tomas"]) + 1,
                "repuesto": repuesto,
                "turnos": turnos,
                "condiciones": condiciones_automaticas(turnos),
            }
            registro["tomas"].append(toma)
            salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n")
            imprimir_toma(toma)
            return toma

        tomas = [await tomar(preguntas, repuesto=False) for _ in range(TOMAS)]
        if not any(
            toma["condiciones"]["por_turno"][1]["llama_a_la_esperada"] for toma in tomas
        ):
            print("\n== en ninguna toma el turno 2 llama al lineal: los repuestos")
            for repuesto in REPUESTOS_TURNO_2:
                for _ in range(TOMAS):
                    await tomar(con_repuesto(preguntas, repuesto), repuesto=True)

    print("\n== resumen: condiciones 1 y 2, sin leer todavía")
    for toma in registro["tomas"]:
        print(f"  toma {toma['toma']}: {toma['condiciones']['cumple_1_y_2']}")
    print(f"\nTodo, con las conversaciones enteras: {salida}")


def elegir(ruta: Path, numero: int, nombre: str) -> None:
    """Pasa la toma elegida a `grabaciones/`, con sus condiciones."""
    registro = json.loads(ruta.read_text(encoding="utf-8"))
    tomas = {toma["toma"]: toma for toma in registro["tomas"]}
    if numero not in tomas:
        sys.exit(f"No hay toma {numero}: hay {sorted(tomas)}.")
    destino = CARPETA / f"{nombre}.json"
    if destino.exists():
        sys.exit(f"{destino} ya existe: se pisaría una grabación.")

    condiciones = registro["condiciones"]
    toma = tomas[numero]
    grabacion = {
        "model": condiciones["modelo"],
        "model_digest": condiciones["digest"],
        "recorded_at": condiciones["fecha"][:10],
        "commit": condiciones["commit"],
        "prompt": {
            "name": condiciones["prompt"],
            "text": condiciones["texto_del_prompt"],
        },
        "takes": {"recorded": len(tomas), "chosen": numero},
        "conditions": {
            **{
                clave: valor
                for clave, valor in condiciones.items()
                if clave
                not in {"modelo", "digest", "commit", "prompt", "texto_del_prompt"}
            },
            "guion": "spikes/grabar_demostracion.py",
            "tomas": str(ruta.resolve().relative_to(RAIZ)),
            "repuesto": toma["repuesto"],
            "condiciones_1_y_2": toma["condiciones"],
        },
        "turns": [
            {"query": turno["query"], "rounds": turno["rounds"]}
            for turno in toma["turnos"]
        ],
    }
    # Que el reproductor la pueda leer, antes de escribirla.
    TypeAdapter(Grabacion).validate_python(grabacion)
    CARPETA.mkdir(exist_ok=True)
    destino.write_text(
        json.dumps(grabacion, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Toma {numero} de {ruta}, en {destino.relative_to(RAIZ)}.")


async def reproducir(nombre: str) -> None:
    """Pasa las consultas de una grabación por el agente, con el reproductor y
    las herramientas de verdad, y dice turno a turno si salió entero lo grabado.

    El historial es el de la pantalla, como al grabar. Un turno se reproduce
    entero si cada vuelta que devolvió el reproductor es la grabada: si en
    alguna los resultados de las herramientas no cuadraron, habrá devuelto la
    frase de que han cambiado.
    """
    ruta = CARPETA / f"{nombre}.json"
    grabacion = TypeAdapter(Grabacion).validate_json(
        await asyncio.to_thread(ruta.read_bytes)
    )
    preguntas = [turno["query"] for turno in grabacion["turns"]]
    grabadora = Grabadora(ReproductorGrabado(ruta))
    config = configuracion(grabadora)
    print(
        f"== {ruta.relative_to(RAIZ)}: {grabacion['model']}, "
        f"{grabacion['recorded_at']}, commit {grabacion['commit']}"
    )

    app = SERVIDOR.streamable_http_app()
    async with app.router.lifespan_context(app):
        mcp_session._http_client = lambda corte: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE, timeout=corte
        )
        turnos = await conversacion(preguntas, grabadora, config)

    fallos = 0
    for numero, (turno, grabado) in enumerate(
        zip(turnos, grabacion["turns"], strict=True), start=1
    ):
        reproducidas = [vuelta["response"] for vuelta in turno["rounds"]]
        grabadas = [vuelta["response"] for vuelta in grabado["rounds"]]
        entero = reproducidas == grabadas
        fallos += not entero
        print(
            f"  turno {numero}: {'entero' if entero else 'NO SE REPRODUCE'} · "
            f"{len(reproducidas)} de {len(grabadas)} vueltas · {turno['estado']} · "
            f"{turno['total_s']} s"
        )
        if not entero:
            print(f"     responde: {turno['respuesta'] or turno['detalle']}")
    if fallos:
        sys.exit(f"{fallos} de {len(turnos)} turnos no reproducen lo grabado.")
    print("Se reproduce entera.")


async def reproducir_en(base: str, nombre: str) -> None:
    """`reproducir`, por la API de un despliegue: lo que verá la pantalla.

    De la traza pública sólo se comparan el texto de cada vuelta del modelo y
    los nombres de lo que pidió: es lo que publica `GET /chat/{id}`. Si los
    resultados de las herramientas no cuadraron, el texto de la vuelta será la
    frase de que han cambiado, y no el grabado.
    """
    ruta = CARPETA / f"{nombre}.json"
    grabacion = TypeAdapter(Grabacion).validate_json(
        await asyncio.to_thread(ruta.read_bytes)
    )
    # El certificado de la pila local lo firma Caddy, y no hay por qué fiarse
    # de él; en cualquier otro sitio, se verifica.
    verificar = httpx.URL(base).host not in {"localhost", "127.0.0.1"}
    async with httpx.AsyncClient(verify=verificar, timeout=30) as cliente:
        agente = (await cliente.get(f"{base}/agent")).raise_for_status().json()
        sirve = agente["recording"]
        esperada = {
            "model": grabacion["model"],
            "recorded_at": grabacion["recorded_at"].isoformat(),
            "commit": grabacion["commit"],
        }
        if sirve != esperada:
            sys.exit(f"{base} no sirve esta grabación: `recording` es {sirve}.")
        print(f"== {base}: sirve la grabación de {ruta.relative_to(RAIZ)}")

        intercambios: list[tuple[str, dict]] = []
        fallos = 0
        for numero, turno in enumerate(grabacion["turns"], start=1):
            historial = historial_que_cabe(
                intercambios,  # pyright: ignore[reportArgumentType]
                agente["max_history_chars"],
            )
            inicio = time.perf_counter()
            aceptada = await cliente.post(
                f"{base}/chat", json={"message": turno["query"], "history": historial}
            )
            identificador = aceptada.raise_for_status().json()["id"]
            while True:
                trabajo = (
                    (await cliente.get(f"{base}/chat/{identificador}"))
                    .raise_for_status()
                    .json()
                )
                if trabajo["status"] == "done":
                    break
                # Cada 2 s, como la pantalla: más deprisa gastaría el límite
                # de peticiones de la API (#169).
                await asyncio.sleep(2)
            segundos = time.perf_counter() - inicio

            vueltas = [paso for paso in trabajo["steps"] if paso["kind"] == "model"]
            grabadas = [vuelta["response"] for vuelta in turno["rounds"]]
            entero = len(vueltas) == len(grabadas) and all(
                vuelta["content"] == grabada["content"]
                and vuelta["tool_calls"]
                == [llamada["name"] for llamada in grabada["tool_calls"]]
                for vuelta, grabada in zip(vueltas, grabadas, strict=True)
            )
            fallos += not entero
            final = trabajo["result"]
            print(
                f"  turno {numero}: {'entero' if entero else 'NO SE REPRODUCE'} · "
                f"{len(vueltas)} de {len(grabadas)} vueltas · {final['status']} · "
                f"{segundos:.1f} s"
            )
            if not entero:
                print(f"     responde: {final['answer'] or final['detail']}")
            intercambios.append(
                (turno["query"], {"answer": final["answer"], "steps": trabajo["steps"]})
            )
    if fallos:
        sys.exit(
            f"{fallos} de {len(grabacion['turns'])} turnos no reproducen lo grabado."
        )
    print("Se reproduce entera.")


async def en_seco() -> None:
    """Lo que se puede comprobar sin modelo, antes de gastar una sesión."""
    preguntas = preguntas_de_la_guia()
    print("== las preguntas de la guía")
    for numero, pregunta in enumerate(preguntas, start=1):
        print(f"  {numero}: {pregunta}")
    print("== los repuestos del turno 2")
    for repuesto in REPUESTOS_TURNO_2:
        print(f"  {con_repuesto(preguntas, repuesto)[1]}")
    print("== los modelos de las señales, contra sus fichas")
    for modelo in comprobar_revisiones():
        print(f"  {modelo['model_id']}: {modelo['revision'][:12]}")
    nombres = {herramienta.name for herramienta in await SERVIDOR.list_tools()}
    print(f"== el catálogo: {len(nombres)} herramientas")
    faltan = set().union(*ESPERADAS) - nombres
    if faltan:
        sys.exit(f"Faltan en el catálogo: {sorted(faltan)}")
    configuracion(Grabadora(cliente_de_ollama()))
    print(
        f"== la configuración: prompt {DEFECTO['llm_prompt']}, num_ctx {DEFECTO['llm_num_ctx']}"
    )
    print("Sin fallos.")


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["--en-seco"]:
            asyncio.run(en_seco())
        case ["--elegir", ruta, numero, *nombre] if len(nombre) <= 1:
            elegir(Path(ruta), int(numero), nombre[0] if nombre else "demostracion")
        case ["--reproducir", *nombre] if len(nombre) <= 1:
            asyncio.run(reproducir(nombre[0] if nombre else "demostracion"))
        case ["--reproducir-en", base, *nombre] if len(nombre) <= 1:
            asyncio.run(
                reproducir_en(base.rstrip("/"), nombre[0] if nombre else "demostracion")
            )
        case [carpeta] if not carpeta.startswith("-"):
            asyncio.run(grabar(Path(carpeta)))
        case _:
            sys.exit(__doc__)
