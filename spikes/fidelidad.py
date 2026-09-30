"""#192 (2026-09-29) - La fidelidad de las respuestas del agente.

La pregunta de #192 es si lo que el agente CUENTA está en lo que devolvieron
las herramientas, y qué prompt lo consigue sin sonar técnico. Se responde por
partes:

1. `corpus`: las conversaciones que después se leen a mano y juzgan los modelos
   jueces. Son 27 consultas completas —hasta seis vueltas y con los resultados
   enteros, como en producción— respondidas por cuatro fuentes:

   - `27b-04`: el 27B razonando con `04-preciso`, lo que hay en producción.
   - `2b-04`: el 2B razonando con `04-preciso`. No es candidato: en el spike de
     la A40 las dos respuestas suyas que se leyeron estaban mal sin que la
     criba lo viera, y está para que haya errores sutiles que cazar.
   - `27b-04-sin-razonar`: el 27B sin razonar, sólo en las 12 consultas de
     análisis. Tampoco es candidato: en #188 se inventaba los resultados, y
     está para que haya errores burdos.
   - `27b-03`: el 27B razonando con `03-estricto`, el otro candidato.

   Van en ese orden, de lo que más importa a lo que menos, por si la sesión de
   GPU se agota antes de terminar.

   Las consultas son las 26 de `agente_a40.py` sin las cinco que no piden
   herramientas —sin resultados no hay nada a lo que ser fiel— y sus seis
   bucles. Cada conversación se guarda entera, con la traza y los resultados,
   porque no sale igual al volver a generarla: sin ella, ni la lectura ni la
   calibración de los jueces se podrían reproducir.

   Cuenta además las llamadas repetidas —la misma herramienta con los mismos
   argumentos dentro de una conversación—, que se vieron en #191. Es un
   recuento, sin juez.

   La temperatura NO se manda, como en producción: el agente no la fija, y el
   modelo usa la de su Modelfile. Por la regla de #188 —un parámetro que no se
   manda también es una condición—, el guion lee esos parámetros de Ollama y
   los guarda con lo demás.

   El servidor MCP es el `mcp` de `backend.main`, servido en proceso como en
   `agente_a40.py`: las herramientas se ejecutan de verdad, con
   NLP_BACKEND=local, y las de noticias llaman a NYT y a Guardian.

2. `jueces`: un modelo juzga cada respuesta del corpus con la rúbrica de
   `spikes/prompts/juez-fidelidad.md`, la misma con la que se hace la lectura a
   mano. Sólo las que tienen texto: una respuesta vacía no tiene nada que leer.
   Aquí, al revés que en el agente, TODO va explícito —`temperature` 0,
   `think` y `num_ctx`—, porque el juez es un instrumento de medida y no
   producción. La salida va atada a un esquema JSON (`format` de Ollama), y el
   guion vuelve a calcular si la respuesta es fiel a partir de las afirmaciones
   que el juez clasificó: si no coincide con lo que él mismo dice, lo marca.
   El primer caso hace de prueba: si el modelo no carga o no devuelve el JSON
   pedido, se para ahí en vez de gastar la sesión. Juzga el corpus o, si se le
   da, otro fichero con la misma forma (los de `comparar`).

3. `comparar`: las mismas 27 consultas, una vez (se diseñó con tres: ver
   `REPETICIONES`), en cinco condiciones —el
   prompt de producción con y sin redondeo de las cifras que lee el modelo,
   `05-llano`, `03-estricto`, y el ganador con el perfil de muestreo «preciso»
   que recomiendan los autores del modelo—. Se intercalan (consulta a
   consulta, todas las condiciones seguidas) para que el paso del tiempo —las
   noticias cambian— no caiga sobre una sola condición. Además de lo que diga
   el juez, cuenta sin juez lo que salió de la validación a mano: nombres
   internos, posiciones y cifras con más de tres decimales en el texto, las
   llamadas repetidas, las que no son las esperadas para la consulta y las
   respuestas sin ninguna herramienta.

4. `resumen`: sin GPU. Las cifras de cada condición, con las del juez si ya
   se ha juzgado, y cuánto dicen los marcadores de la legibilidad leída a
   mano en el corpus. La regla para decidir se fijó ANTES de medir y está en
   la sección del README.

5. `validar` y `calibrar`: sin GPU. La lectura de Claude la valida el autor en
   una página aparte; `validar` copia esas decisiones, exportadas, al campo
   `validada` de `lectura.json`, y `calibrar` mide contra ellas a cada juez, a
   las parejas de jueces y a la propia lectura: cuántas infieles caza, cuántas
   fieles da por infieles, el kappa y la legibilidad.

6. `ventana`: las dos vueltas más pesadas de la comparación, con el historial
   máximo que admite la API, con `num_ctx` 8.192 y 16.384: si la pequeña
   recorta, y cuánta memoria cuesta la grande. Mide antes de cambiar el valor
   por defecto del agente. Con argumentos, repite las consultas que se le den
   en las ventanas que se le den, y guarda cada traza entera con el
   razonamiento del modelo, para explicar una respuesta vacía.

Ejecutar desde la raíz, con el túnel abierto (la sesión la abre
`spikes/fidelidad_a40.sh`):

    NLP_BACKEND=local .venv/bin/python spikes/fidelidad.py corpus [fuente ...]
    .venv/bin/python spikes/fidelidad.py jueces <modelo> [fichero]
    NLP_BACKEND=local .venv/bin/python spikes/fidelidad.py comparar A B C D
    NLP_BACKEND=local .venv/bin/python spikes/fidelidad.py comparar E:05-llano
    .venv/bin/python spikes/fidelidad.py resumen
    .venv/bin/python spikes/fidelidad.py validar <carpeta exportada>
    .venv/bin/python spikes/fidelidad.py calibrar
    NLP_BACKEND=local .venv/bin/python spikes/fidelidad.py ventana
    NLP_BACKEND=local .venv/bin/python spikes/fidelidad.py ventana --ctx 16384 --veces 3 bucle-encadena-nyt

Sin fuentes, las cuatro; los jueces, de uno en uno; `E:<prompt>` es la
condición del perfil preciso sobre ese prompt. `OLLAMA_URL` cambia el servidor
(defecto `http://127.0.0.1:11500`) y `FIDELIDAD_JSON` el fichero del corpus o
del juez (defecto `spikes/fidelidad/corpus.json` y
`spikes/fidelidad/juez-<modelo>[-<fichero>].json`). Los de `comparar` son
`spikes/fidelidad/comparacion-<condición>.json`, y continúan donde se quedaron.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import statistics
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import httpx
import structlog

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Los guiones del spike leen `sys.argv` AL IMPORTARSE (modelo y `num_ctx`), y
# con los argumentos de éste fallarían. Se importan con la línea vacía y se
# devuelve después, como en `agente_a40.py`.
_ARGUMENTOS, sys.argv = sys.argv, sys.argv[:1]
from backend.agent import agente, prompts  # noqa: E402
from backend.agent.agente import Configuracion, responder  # noqa: E402
from backend.config.settings import settings  # noqa: E402
from backend.core.mcp import session as mcp_session  # noqa: E402
from backend.integrations.llm.ollama import OllamaClient  # noqa: E402
from backend.main import mcp as SERVIDOR  # noqa: E402
from spikes.agente_a40 import BUCLES  # noqa: E402
from spikes.tool_calling_descripciones_contraste import (  # noqa: E402
    CONSULTAS as CONTRASTE,
)
from spikes.tool_calling_fase2 import CLICKBAIT_CUALQUIERA, PRUEBAS  # noqa: E402

sys.argv = _ARGUMENTOS

# Sólo avisos: lo que importa de cada conversación ya va en lo que se imprime.
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
for ruidoso in ("httpx", "mcp", "backend"):
    logging.getLogger(ruidoso).setLevel(logging.WARNING)

URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11500")
NUM_CTX = 8192
KEEP_ALIVE = "10m"
# El `llm_timeout` de producción desde #188: una vuelta llegó a tardar 96 s.
LLM_TIMEOUT = 300.0
CARPETA = RAIZ / "spikes" / "fidelidad"
CORPUS = CARPETA / "corpus.json"
RUBRICA = RAIZ / "spikes" / "prompts" / "juez-fidelidad.md"

# El juez es un instrumento de medida: todo explícito. La ventana es el doble
# que la del agente porque cada caso lleva los resultados enteros de todas las
# herramientas de la conversación, más la rúbrica.
JUEZ_NUM_CTX = 16384
JUEZ_TEMPERATURA = 0
JUEZ_THINK = True

CLASIFICACIONES = ["respaldada", "mal_atribuida", "contradicha", "inventada"]
# Lo que tiene que devolver el juez; Ollama lo impone al generar (`format`).
ESQUEMA_JUICIO = {
    "type": "object",
    "properties": {
        "afirmaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string"},
                    # Vacía si la afirmación no se atribuye a ninguna herramienta.
                    "herramienta": {"type": "string"},
                    "clasificacion": {"type": "string", "enum": CLASIFICACIONES},
                    "motivo": {"type": "string"},
                },
                "required": ["texto", "herramienta", "clasificacion", "motivo"],
            },
        },
        "fiel": {"type": "boolean"},
        "legibilidad": {"type": "integer", "enum": [1, 2, 3]},
        "motivo_legibilidad": {"type": "string"},
    },
    "required": ["afirmaciones", "fiel", "legibilidad", "motivo_legibilidad"],
}

_BASE = "http://127.0.0.1:8765"
_SERVIDOR_URL = f"{_BASE}/mcp"


@dataclass(frozen=True)
class Fuente:
    """Quién responde: un modelo, un prompt, si razona y a qué consultas."""

    nombre: str
    modelo: str
    prompt: str
    think: bool
    solo_analisis: bool = False


FUENTES = [
    Fuente("27b-04", "qwen3.5:27b", "04-preciso", think=True),
    Fuente("2b-04", "qwen3.5:2b", "04-preciso", think=True),
    Fuente("27b-04-sin-razonar", "qwen3.5:27b", "04-preciso", think=False, solo_analisis=True),
    Fuente("27b-03", "qwen3.5:27b", "03-estricto", think=True),
]

# Las que piden analizar un titular: las que respondió inventando en #188.
CATEGORIAS_DE_ANALISIS = ("GENERICA", "ESPECIFICA")

# Qué herramientas pide cada consulta. Las 21 del spike lo traen de su guion (en
# las genéricas vale también `analyze_headline`, como en `agente_a40.py`); los
# bucles, de lo que piden en palabras. Cualquier otra llamada es «de más».
_ANALISIS = CLICKBAIT_CUALQUIERA | {"analyze_headline"}
ESPERADAS_BUCLES = {
    "encadena-nyt": {"get_nyt_news"} | _ANALISIS,
    "dos-senales": {"detect_clickbait_lexical", "detect_clickbait_linear"},
    "analisis-completo": _ANALISIS | {"detect_clickbait_incoherence", "analyze_sentiment"},
    "incoherencia": {"detect_clickbait_incoherence", "analyze_headline"},
    "encadena-guardian": {"get_guardian_news"} | _ANALISIS,
    "segundo-turno": {"detect_clickbait"},
}


def _consultas() -> list[tuple[str, str, str, list, set]]:
    """Las 27 consultas, como (clave, categoría, consulta, historial, esperadas).

    La clave es estable —la categoría y su número de orden, o el nombre del
    bucle— para que la lectura a mano y los jueces se refieran a lo mismo.
    """
    filas = [
        (categoria, consulta, _ANALISIS if categoria == "GENERICA" else set(esperadas))
        for categoria, consulta, esperadas in PRUEBAS
        if categoria != "SIN_TOOL"
    ]
    filas += [("CONTRASTE", consulta, set(esperadas)) for _, consulta, esperadas in CONTRASTE]
    numero = Counter()
    consultas = []
    for categoria, consulta, esperadas in filas:
        numero[categoria] += 1
        consultas.append((f"{categoria.lower()}-{numero[categoria]}", categoria, consulta, [], esperadas))
    consultas += [
        (f"bucle-{nombre}", "BUCLE", consulta, historial, ESPERADAS_BUCLES[nombre])
        for nombre, consulta, historial in BUCLES
    ]
    return consultas


class OllamaConMuestreo(OllamaClient):
    """El cliente del agente, mandando además el muestreo que se le dé.

    Para la condición del perfil «preciso» sin tocar el backend: si gana, el
    muestreo pasará a ser configuración explícita del agente, como `num_ctx`.
    """

    def __init__(self, *args, muestreo: dict, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.muestreo = muestreo

    async def make_request(self, endpoint, method, params=None, json=None):
        if json is not None:
            json = {**json, "options": {**json.get("options", {}), **self.muestreo}}
        return await super().make_request(endpoint, method, params=params, json=json)


class OllamaQueGuardaElRazonamiento(OllamaConMuestreo):
    """El mismo cliente, guardando lo que Ollama devuelve y el agente descarta.

    La traza del agente no lleva el razonamiento del modelo —el cliente no lo
    lee—, y un `empty_answer` sólo se explica leyéndolo: en la primera medida
    de `ventana` hubo uno que no era de la ventana, y no quedó nada con que
    explicarlo. `done_reason` dice si paró el modelo (`stop`) o se acabó la
    ventana (`length`).
    """

    def __init__(self, *args, muestreo: dict | None = None, **kwargs) -> None:
        super().__init__(*args, muestreo=muestreo or {}, **kwargs)
        self.crudo: list[dict] = []

    async def make_request(self, endpoint, method, params=None, json=None):
        resultado = await super().make_request(endpoint, method, params=params, json=json)
        if resultado.success and isinstance(resultado.data, dict):
            mensaje = resultado.data.get("message") or {}
            self.crudo.append(
                {
                    "done_reason": resultado.data.get("done_reason"),
                    "thinking": mensaje.get("thinking"),
                    "content": mensaje.get("content"),
                    "tool_calls": mensaje.get("tool_calls"),
                }
            )
        return resultado


def _config(
    fuente: Fuente,
    decimales: int | None = None,
    muestreo: dict | None = None,
    num_ctx: int = NUM_CTX,
    clase: type[OllamaClient] | None = None,
) -> Configuracion:
    """La configuración del agente de producción, con el modelo, el prompt y el
    `think` de la fuente.

    El redondeo va explícito: el corpus se generó antes de que existiera
    (`239a955`), y sin decirlo aquí, repetirlo hoy redondearía.
    """
    clase = clase or (OllamaConMuestreo if muestreo else OllamaClient)
    extra = {"muestreo": muestreo} if muestreo else {}
    return Configuracion(
        backend=clase(
            URL, fuente.modelo, num_ctx=num_ctx, keep_alive=KEEP_ALIVE, timeout=LLM_TIMEOUT, **extra
        ),
        servers=[_SERVIDOR_URL],
        prompt=prompts.cargar(fuente.prompt),
        discovery_timeout=10.0,
        # Las señales locales cargan su modelo la primera vez que se usan.
        execute_timeout=120.0,
        think=fuente.think,
        decimales_para_el_modelo=decimales,
    )


@dataclass(frozen=True)
class Condicion:
    """Una condición de la comparación: el prompt, el redondeo y el muestreo.

    `muestreo` es `None` cuando no se manda nada, como en producción: entonces
    manda el Modelfile, que se lee y se anota en las condiciones.
    """

    nombre: str
    prompt: str
    decimales: int | None
    muestreo: dict | None = None
    modelo: str = "qwen3.5:27b"


# El perfil que recomiendan los autores de Qwen3.5 para tareas precisas; el del
# Modelfile (temperatura 1, presence_penalty 1,5) es el de tareas generales.
PERFIL_PRECISO = {"temperature": 0.6, "presence_penalty": 0.0}
CONDICIONES = {
    "A": Condicion("A-04-sin-redondeo", "04-preciso", decimales=None),
    "B": Condicion("B-04", "04-preciso", decimales=3),
    "C": Condicion("C-05", "05-llano", decimales=3),
    "D": Condicion("D-03", "03-estricto", decimales=3),
}
# Una: decidido por el usuario el 2026-09-29, con la primera sesión ya en marcha
# (se diseñó con tres). Juzgar cada conversación con el juez calibrado cuesta
# ~70 s, y la segunda y la tercera sólo habrían dado marcadores sin juez. La
# primera sesión se paró al completar la repetición 1, así que sus ficheros
# dicen `"repeticiones": 3` en las condiciones pero sólo traen `r1`.
REPETICIONES = 1
FALLOS_SEGUIDOS_PARA_PARAR = 3


def _condicion(nombre: str) -> Condicion:
    """`A`–`D`, o `E:<prompt>`: el perfil preciso sobre el prompt ganador."""
    if nombre.startswith("E:"):
        prompt = nombre.removeprefix("E:")
        if prompt not in prompts.disponibles():
            sys.exit(f"No hay ningún prompt «{prompt}». Hay: {prompts.disponibles()}")
        return Condicion(f"E-{prompt[:2]}-preciso", prompt, decimales=3, muestreo=PERFIL_PRECISO)
    if nombre not in CONDICIONES:
        sys.exit(f"Condición desconocida: {nombre}. Hay: {list(CONDICIONES)} y E:<prompt>")
    return CONDICIONES[nombre]


# Lo que la validación a mano señaló como técnico (#192), contado en el texto sin
# juez. Los nombres internos van en `snake_case` —herramientas, categorías,
# veredictos—, son las categorías de una palabra y el campo `score`, o son
# etiquetas en inglés; «neutral» no, que es también castellano.
MARCADORES = {
    "nombres_internos": re.compile(
        r"\b[a-z]+(?:_[a-z]+)+\b|\b(?:hyperbole|question|ellipsis|score)\b"
        r"|\bfactual news\b|\bpositive\b|\bnegative\b",
        re.IGNORECASE,
    ),
    "posiciones": re.compile(r"\[\s*\d+\s*[,\-–]\s*\d+\s*\]|posici(?:ón|ones)\s+\[?\d", re.IGNORECASE),
    "decimales_largos": re.compile(r"\d[.,]\d{4,}"),
}


def _marcadores(texto: str) -> dict:
    return {nombre: len(patron.findall(texto)) for nombre, patron in MARCADORES.items()}


def _de_mas(pasos: list, esperadas: set) -> list[str]:
    """Las llamadas a herramientas que la consulta no pedía (#192, validación)."""
    return [paso["name"] for paso in pasos if paso["kind"] == "tool" and paso["name"] not in esperadas]


def _repetidas(pasos: list) -> list[dict]:
    """Las llamadas que se repiten con los mismos argumentos, y cuántas veces (#191)."""
    veces = Counter(
        (paso["name"], json.dumps(paso["arguments"], sort_keys=True, ensure_ascii=False))
        for paso in pasos
        if paso["kind"] == "tool"
    )
    return [
        {"name": nombre, "arguments": json.loads(argumentos), "veces": cuantas}
        for (nombre, argumentos), cuantas in veces.items()
        if cuantas > 1
    ]


def _conversacion(
    fuente: Fuente, clave: str, categoria: str, consulta: str, historial: list, resultado: dict
) -> dict:
    """Todo lo que trae una conversación, con la traza entera (#189: lo que no se guarda no se explica)."""
    vueltas = [paso for paso in resultado["steps"] if paso["kind"] == "model"]
    return {
        "id": f"{fuente.nombre}/{clave}",
        "fuente": fuente.nombre,
        "categoria": categoria,
        "consulta": consulta,
        "historial": historial,
        "estado": resultado["status"],
        "detalle": resultado["detail"],
        "respuesta": resultado["answer"],
        "herramientas": [paso["name"] for paso in resultado["steps"] if paso["kind"] == "tool"],
        "repetidas": _repetidas(resultado["steps"]),
        "vueltas": [
            {
                "prompt_tokens": vuelta["metrics"]["prompt_tokens"],
                "output_tokens": vuelta["metrics"]["output_tokens"],
                "load_s": vuelta["metrics"]["load_s"],
                "total_s": vuelta["metrics"]["total_s"],
                "pide": vuelta["tool_calls"],
            }
            for vuelta in vueltas
        ],
        "total_s": resultado["total_s"],
        "pasos": resultado["steps"],
    }


def _guardar(registro: dict, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(registro, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8"
    )


def _mediana(valores: list[float]) -> float:
    return statistics.median(valores) if valores else float("nan")


def _huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]


# ----- Las condiciones -----


async def _pedir(cliente: httpx.AsyncClient, metodo: str, ruta: str, cuerpo: dict | None = None):
    """Una consulta a Ollama que no hace fallar el guion: sin respuesta, `None`."""
    try:
        respuesta = await cliente.request(metodo, f"{URL}/{ruta}", json=cuerpo)
        respuesta.raise_for_status()
        return respuesta.json()
    except (httpx.HTTPError, ValueError) as error:
        print(f"  (sin respuesta de {ruta}: {type(error).__name__})")
        return None


async def _condiciones(modelos_usados: set[str]) -> dict:
    """Lo común a las dos partes para situar y repetir la medida: el momento, el
    código, la versión de Ollama y cada modelo, con los parámetros que no se mandan."""
    async with httpx.AsyncClient(timeout=10.0) as cliente:
        version = await _pedir(cliente, "GET", "api/version") or {}
        etiquetas = await _pedir(cliente, "GET", "api/tags") or {}
        modelos = {}
        for modelo in sorted(modelos_usados):
            ficha = await _pedir(cliente, "POST", "api/show", {"model": modelo}) or {}
            digest = next(
                (
                    entrada.get("digest")
                    for entrada in etiquetas.get("models", [])
                    if entrada.get("name") == modelo
                ),
                None,
            )
            modelos[modelo] = {
                "id": digest[:12] if digest else None,
                # La temperatura y el resto del muestreo del Modelfile: el agente
                # no los manda, y el juez manda sólo la temperatura.
                "parametros": ficha.get("parameters"),
            }
    return {
        "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
        "commit": subprocess.run(
            ["git", "-C", str(RAIZ), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip(),
        "guion": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12],
        "ollama": version.get("version"),
        "servidor": URL,
        "modelos": modelos,
    }


async def _condiciones_del_corpus(fuentes: list[Fuente]) -> dict:
    return await _condiciones({fuente.modelo for fuente in fuentes}) | {
        "num_ctx": NUM_CTX,
        "keep_alive": KEEP_ALIVE,
        "nlp_backend": settings.nlp_backend,
        "prompts": {
            nombre: _huella(prompts.cargar(nombre))
            for nombre in sorted({fuente.prompt for fuente in fuentes})
        },
        "fuentes": [asdict(fuente) for fuente in fuentes],
    }


# ----- 1 · El corpus -----


def _resumir(fuente: Fuente, conversaciones: list[dict]) -> None:
    estados = Counter(conversacion["estado"] for conversacion in conversaciones)
    tiempos = [conversacion["total_s"] for conversacion in conversaciones]
    vueltas = [len(conversacion["vueltas"]) for conversacion in conversaciones]
    con_repetidas = [conversacion for conversacion in conversaciones if conversacion["repetidas"]]
    llamadas_de_mas = sum(
        repetida["veces"] - 1
        for conversacion in con_repetidas
        for repetida in conversacion["repetidas"]
    )
    print(f"  -- {fuente.nombre}: {dict(estados)}")
    print(
        f"     de punta a punta: mediana {_mediana(tiempos):.1f} s · máx {max(tiempos, default=0):.1f} s"
        f" · vueltas, mediana {_mediana(vueltas):.0f}"
    )
    print(
        f"     llamadas repetidas: {llamadas_de_mas} de más, en {len(con_repetidas)} de "
        f"{len(conversaciones)} conversaciones"
    )


async def corpus(registro: dict, fuentes: list[Fuente], ruta: Path) -> None:
    catalogo = await agente._descubrir(_config(fuentes[0]))
    registro["condiciones"]["herramientas"] = sorted(catalogo)
    print(f"  {len(catalogo)} herramientas: {', '.join(sorted(catalogo))}")

    consultas = _consultas()
    registro["conversaciones"] = []
    for fuente in fuentes:
        elegidas = [
            fila
            for fila in consultas
            if not fuente.solo_analisis or fila[1] in CATEGORIAS_DE_ANALISIS
        ]
        print(
            f"\n== {fuente.nombre}: {fuente.modelo}, `{fuente.prompt}`, think {fuente.think}"
            f" · {len(elegidas)} consultas"
        )
        for clave, categoria, consulta, historial, _ in elegidas:
            resultado = await responder(consulta, historial, _config(fuente))
            conversacion = _conversacion(fuente, clave, categoria, consulta, historial, resultado)
            registro["conversaciones"].append(conversacion)
            _guardar(registro, ruta)
            repetidas = "".join(
                f" · REPITE {repetida['name']} ×{repetida['veces']}"
                for repetida in conversacion["repetidas"]
            )
            print(
                f"  {conversacion['estado']:12} {conversacion['total_s']:6.1f} s "
                f"{len(conversacion['vueltas'])} v  {clave:28} "
                f"{conversacion['herramientas'] or '-'}{repetidas}"
                + (f" · {conversacion['detalle']}" if conversacion["detalle"] else "")
            )
        _resumir(
            fuente,
            [
                conversacion
                for conversacion in registro["conversaciones"]
                if conversacion["fuente"] == fuente.nombre
            ],
        )


# ----- 2 · Los jueces -----


def _caso(conversacion: dict) -> str:
    """Lo que lee el juez: la consulta, los turnos anteriores, cada herramienta
    con su resultado ENTERO o su error, y la respuesta. Nada del razonamiento
    del agente ni de sus vueltas: se juzga lo que leería quien usa la pantalla."""
    bloques = [f"## Consulta\n\n{conversacion['consulta']}"]
    if conversacion["historial"]:
        turnos = "\n".join(
            f"- {turno['role']}: {turno['content']}" for turno in conversacion["historial"]
        )
        bloques.append(f"## Turnos anteriores\n\n{turnos}")
    llamadas = [paso for paso in conversacion["pasos"] if paso["kind"] == "tool"]
    resultados = ["## Resultados de las herramientas"]
    if not llamadas:
        resultados.append("No se llamó a ninguna herramienta.")
    for numero, llamada in enumerate(llamadas, 1):
        cabecera = f"### {numero}. {llamada['name']}({json.dumps(llamada['arguments'], ensure_ascii=False)})"
        if llamada["status"] == "ok":
            datos = json.dumps(llamada["data"], ensure_ascii=False, indent=1, default=str)
            resultados.append(f"{cabecera}\n\n```json\n{datos}\n```")
        else:
            resultados.append(f"{cabecera}\n\nError: {llamada['error']}")
    bloques.append("\n\n".join(resultados))
    bloques.append(f"## Respuesta del asistente\n\n{conversacion['respuesta']}")
    return "\n\n".join(bloques)


def _leer_juicio(contenido: str) -> dict | None:
    """El JSON del juez, o `None` si no tiene la forma pedida."""
    try:
        juicio = json.loads(contenido)
    except ValueError:
        return None
    if not isinstance(juicio, dict) or any(clave not in juicio for clave in ESQUEMA_JUICIO["required"]):
        return None
    return juicio


async def _juzgar(cliente: httpx.AsyncClient, modelo: str, rubrica: str, conversacion: dict) -> dict:
    caso = _caso(conversacion)
    cuerpo = {
        "model": modelo,
        "stream": False,
        "think": JUEZ_THINK,
        "keep_alive": KEEP_ALIVE,
        "format": ESQUEMA_JUICIO,
        "options": {"temperature": JUEZ_TEMPERATURA, "num_ctx": JUEZ_NUM_CTX},
        "messages": [
            {"role": "system", "content": rubrica},
            {"role": "user", "content": caso},
        ],
    }
    fila: dict = {"id": conversacion["id"], "fuente": conversacion["fuente"], "caracteres": len(caso)}
    try:
        respuesta = await cliente.post(f"{URL}/api/chat", json=cuerpo, timeout=LLM_TIMEOUT)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (httpx.HTTPError, ValueError) as error:
        # El cuerpo del error de Ollama dice por qué (un modelo que no carga,
        # un `think` que no admite): se guarda para leerlo.
        detalle = getattr(getattr(error, "response", None), "text", "")[:500]
        return fila | {"error": f"{type(error).__name__}: {detalle}"}

    mensaje = datos.get("message", {})
    juicio = _leer_juicio(mensaje.get("content", ""))
    prompt_tokens = datos.get("prompt_eval_count") or 0
    salida_tokens = datos.get("eval_count") or 0
    fila |= {
        "error": None,
        "json_valido": juicio is not None,
        "juicio": juicio,
        "crudo": None if juicio else mensaje.get("content", ""),
        "pensamiento": mensaje.get("thinking", ""),
        "prompt_tokens": prompt_tokens,
        "output_tokens": salida_tokens,
        "load_s": (datos.get("load_duration") or 0) / 1e9,
        "total_s": (datos.get("total_duration") or 0) / 1e9,
        # Ollama recorta en silencio lo que no cabe (spike de la A40): si la
        # conversación llena la ventana, el juez puede no haber leído todo.
        "posible_recorte": prompt_tokens + salida_tokens >= JUEZ_NUM_CTX,
    }
    if juicio:
        sin_respaldo = [
            afirmacion
            for afirmacion in juicio["afirmaciones"]
            if afirmacion.get("clasificacion") != "respaldada"
        ]
        fila["fiel_recalculado"] = not sin_respaldo
        fila["sin_respaldo"] = len(sin_respaldo)
        fila["se_contradice"] = juicio["fiel"] != fila["fiel_recalculado"]
    return fila


def _resumir_juez(juicios: list[dict]) -> None:
    por_fuente: dict[str, list[dict]] = {}
    for juicio in juicios:
        por_fuente.setdefault(juicio["fuente"], []).append(juicio)
    for fuente, filas in por_fuente.items():
        validos = [fila for fila in filas if fila.get("json_valido")]
        fieles = sum(fila["fiel_recalculado"] for fila in validos)
        legibilidad = Counter(fila["juicio"]["legibilidad"] for fila in validos)
        print(
            f"  -- {fuente}: fieles {fieles}/{len(validos)} · legibilidad {dict(sorted(legibilidad.items()))}"
            f" · se contradice {sum(fila['se_contradice'] for fila in validos)}"
            f" · JSON no válido {sum(not fila.get('json_valido') for fila in filas if not fila['error'])}"
            f" · errores {sum(bool(fila['error']) for fila in filas)}"
        )
    tiempos = [juicio["total_s"] for juicio in juicios if not juicio["error"]]
    print(
        f"  por caso: mediana {_mediana(tiempos):.1f} s · máx {max(tiempos, default=0):.1f} s · "
        f"prompt_tokens máx {max((juicio.get('prompt_tokens', 0) for juicio in juicios), default=0)} "
        f"de {JUEZ_NUM_CTX} · posibles recortes {sum(bool(juicio.get('posible_recorte')) for juicio in juicios)}"
    )


# Lo que tiene que coincidir para que una sesión continúe la anterior del mismo
# juez: si cambia algo de esto, los juicios no son de la misma medida.
CONDICIONES_FIJAS_DEL_JUEZ = ("juez", "num_ctx", "temperature", "think", "rubrica", "corpus")
ERRORES_SEGUIDOS_PARA_PARAR = 3


async def jueces(modelo: str, ruta: Path, juzgado: Path = CORPUS) -> None:
    """Un juez sobre el corpus, o sobre otro fichero con su forma, en una o
    varias sesiones.

    Juzgar es lento —el juez razona y escribe cada afirmación—, así que un juez
    puede no caber en una sesión corta de GPU. Si ya hay un fichero de este
    juez con las mismas condiciones fijas, se continúa: se conservan los
    juicios hechos (también los de JSON no válido, que son un resultado) y se
    repiten sólo los que fallaron por error. Cada sesión queda anotada.
    """
    corpus_leido = json.loads(juzgado.read_text(encoding="utf-8"))
    casos = [
        conversacion
        for conversacion in corpus_leido["conversaciones"]
        if conversacion["estado"] == "answered" and conversacion["respuesta"].strip()
    ]
    rubrica = RUBRICA.read_text(encoding="utf-8")
    condiciones = await _condiciones({modelo}) | {
        "juez": modelo,
        "num_ctx": JUEZ_NUM_CTX,
        "temperature": JUEZ_TEMPERATURA,
        "think": JUEZ_THINK,
        "keep_alive": KEEP_ALIVE,
        "rubrica": _huella(rubrica),
        "corpus": hashlib.sha256(juzgado.read_bytes()).hexdigest()[:12],
        "corpus_generado": corpus_leido["condiciones"]["fecha"],
    } | ({} if juzgado == CORPUS else {"juzgado": juzgado.name})
    for clave, valor in condiciones.items():
        print(f"  {clave}: {valor}")

    if ruta.exists():
        registro = json.loads(ruta.read_text(encoding="utf-8"))
        distintas = [
            clave
            for clave in CONDICIONES_FIJAS_DEL_JUEZ
            if registro["condiciones"].get(clave) != condiciones[clave]
        ]
        if distintas:
            sys.exit(
                f"ABORTADO: {ruta} es de otra medida (cambia {distintas}). "
                "Se aparta a mano o se usa FIDELIDAD_JSON."
            )
        registro["juicios"] = [fila for fila in registro["juicios"] if not fila["error"]]
    else:
        registro = {"condiciones": condiciones, "sesiones": [], "juicios": []}
    registro["sesiones"].append(
        {clave: condiciones[clave] for clave in ("fecha", "commit", "guion", "ollama")}
        | {"modelo_id": condiciones["modelos"][modelo]["id"]}
    )
    hechos = {fila["id"] for fila in registro["juicios"]}
    pendientes = [conversacion for conversacion in casos if conversacion["id"] not in hechos]
    print(
        f"\n== {modelo}: {len(casos)} respuestas con texto · {len(hechos)} ya juzgadas · "
        f"{len(pendientes)} en esta sesión (la {len(registro['sesiones'])}.ª)"
    )

    errores_seguidos = 0
    async with httpx.AsyncClient() as cliente:
        for numero, conversacion in enumerate(pendientes, 1):
            fila = await _juzgar(cliente, modelo, rubrica, conversacion)
            registro["juicios"].append(fila)
            _guardar(registro, ruta)
            errores_seguidos = errores_seguidos + 1 if fila["error"] else 0
            if fila["error"]:
                print(f"  ERROR  {fila['id']}: {fila['error']}")
            elif not fila["json_valido"]:
                print(f"  JSON NO VÁLIDO  {fila['id']}: {str(fila['crudo'])[:200]!r}")
            else:
                marcas = "".join(
                    [
                        " · SE CONTRADICE" if fila["se_contradice"] else "",
                        " · POSIBLE RECORTE" if fila["posible_recorte"] else "",
                        "" if fila["pensamiento"] else " · sin razonamiento",
                    ]
                )
                print(
                    f"  {'fiel  ' if fila['fiel_recalculado'] else 'INFIEL'} leg {fila['juicio']['legibilidad']} "
                    f"· {fila['sin_respaldo']}/{len(fila['juicio']['afirmaciones'])} sin respaldo "
                    f"· {fila['total_s']:5.1f} s  {fila['id']}{marcas}"
                )
            # El primer caso hace de prueba: si el modelo no carga o no contesta
            # con el JSON pedido, no se gasta la sesión en los demás.
            if numero == 1 and (fila["error"] or not fila["json_valido"]):
                sys.exit("ABORTADO: el primer caso no dio un juicio válido; ver arriba.")
            # Varios errores seguidos son la sesión que se acabó o un servidor
            # caído: se para, y la próxima sesión los repite.
            if errores_seguidos >= ERRORES_SEGUIDOS_PARA_PARAR:
                print(f"  PARADO: {errores_seguidos} errores seguidos; se repiten en la próxima sesión.")
                break
    _resumir_juez(registro["juicios"])
    faltan = len(casos) - len({fila["id"] for fila in registro["juicios"] if not fila["error"]})
    print(f"  {'COMPLETO' if not faltan else f'FALTAN {faltan}: otra sesión con el mismo juez'}")


# ----- 3 · La comparación -----

# Lo que tiene que coincidir para que una sesión continúe la anterior de la
# misma condición.
CONDICIONES_FIJAS_DE_LA_COMPARACION = ("condicion", "prompt_huella", "modelo_id")


def _ruta_de(condicion: Condicion) -> Path:
    return CARPETA / f"comparacion-{condicion.nombre}.json"


async def _registro_de(condicion: Condicion) -> dict:
    """El fichero de una condición: el que había, si es de la misma medida, o uno nuevo."""
    condiciones = await _condiciones({condicion.modelo}) | {
        "condicion": asdict(condicion),
        "prompt_huella": _huella(prompts.cargar(condicion.prompt)),
        "num_ctx": NUM_CTX,
        "keep_alive": KEEP_ALIVE,
        "nlp_backend": settings.nlp_backend,
        "repeticiones": REPETICIONES,
    }
    condiciones["modelo_id"] = condiciones["modelos"][condicion.modelo]["id"]
    ruta = _ruta_de(condicion)
    if ruta.exists():
        registro = json.loads(ruta.read_text(encoding="utf-8"))
        distintas = [
            clave
            for clave in CONDICIONES_FIJAS_DE_LA_COMPARACION
            if registro["condiciones"].get(clave) != condiciones[clave]
        ]
        if distintas:
            sys.exit(f"ABORTADO: {ruta} es de otra medida (cambia {distintas}). Se aparta a mano.")
        # Lo que falló (la sesión que se acabó) se repite.
        registro["conversaciones"] = [
            conversacion for conversacion in registro["conversaciones"] if conversacion["estado"] != "failed"
        ]
    else:
        registro = {"condiciones": condiciones, "sesiones": [], "conversaciones": []}
    registro["sesiones"].append({clave: condiciones[clave] for clave in ("fecha", "commit", "guion", "ollama")})
    return registro


async def comparar(condiciones: list[Condicion]) -> None:
    registros = {condicion.nombre: await _registro_de(condicion) for condicion in condiciones}
    for condicion in condiciones:
        print(f"  {condicion.nombre}: {asdict(condicion)} · {len(registros[condicion.nombre]['conversaciones'])} ya hechas")
    hechas = {
        conversacion["id"]
        for registro in registros.values()
        for conversacion in registro["conversaciones"]
    }
    consultas = _consultas()
    total = REPETICIONES * len(consultas) * len(condiciones)
    print(f"\n== {total - len(hechas)} conversaciones pendientes de {total}")

    fallos_seguidos = 0
    for repeticion in range(1, REPETICIONES + 1):
        for clave, categoria, consulta, historial, esperadas in consultas:
            for condicion in condiciones:
                fuente = Fuente(condicion.nombre, condicion.modelo, condicion.prompt, think=True)
                clave_repetida = f"{clave}/r{repeticion}"
                if f"{condicion.nombre}/{clave_repetida}" in hechas:
                    continue
                resultado = await responder(
                    consulta, historial, _config(fuente, condicion.decimales, condicion.muestreo)
                )
                conversacion = _conversacion(fuente, clave_repetida, categoria, consulta, historial, resultado)
                de_mas = _de_mas(resultado["steps"], esperadas)
                conversacion |= {
                    "repeticion": repeticion,
                    "esperadas": sorted(esperadas),
                    "de_mas": de_mas,
                    "sin_herramientas": resultado["status"] == "answered" and not conversacion["herramientas"],
                    "marcadores": _marcadores(resultado["answer"]),
                }
                registro = registros[condicion.nombre]
                registro["conversaciones"].append(conversacion)
                _guardar(registro, _ruta_de(condicion))
                marcadores = sum(conversacion["marcadores"].values())
                print(
                    f"  {conversacion['estado']:12} {conversacion['total_s']:6.1f} s  {conversacion['id']:48} "
                    f"marcadores {marcadores}"
                    + (f" · DE MÁS {de_mas}" if de_mas else "")
                    + (" · SIN HERRAMIENTAS" if conversacion["sin_herramientas"] else "")
                    + "".join(f" · REPITE {repetida['name']}" for repetida in conversacion["repetidas"])
                    + (f" · {conversacion['detalle']}" if conversacion["detalle"] else "")
                )
                fallos_seguidos = fallos_seguidos + 1 if resultado["status"] == "failed" else 0
                if fallos_seguidos >= FALLOS_SEGUIDOS_PARA_PARAR:
                    print(f"  PARADO: {fallos_seguidos} fallos seguidos; se repiten en la próxima sesión.")
                    return
    print("  COMPLETO")


# ----- 4 · El resumen -----


def _resumen_de(conversaciones: list[dict]) -> dict:
    """Las cifras de una condición que no necesitan juez."""
    contestadas = [conversacion for conversacion in conversaciones if conversacion["estado"] == "answered"]
    marcadores = [sum(conversacion["marcadores"].values()) for conversacion in contestadas]
    return {
        "conversaciones": len(conversaciones),
        "estados": dict(Counter(conversacion["estado"] for conversacion in conversaciones)),
        "marcadores_por_respuesta": round(statistics.mean(marcadores), 2) if marcadores else None,
        "respuestas_sin_marcadores": sum(total == 0 for total in marcadores),
        "marcadores_por_tipo": {
            tipo: sum(conversacion["marcadores"][tipo] for conversacion in contestadas) for tipo in MARCADORES
        },
        "sin_herramientas": sum(conversacion["sin_herramientas"] for conversacion in conversaciones),
        "con_llamadas_de_mas": sum(bool(conversacion["de_mas"]) for conversacion in conversaciones),
        "con_repetidas": sum(bool(conversacion["repetidas"]) for conversacion in conversaciones),
        "tiempo_mediana_s": round(_mediana([conversacion["total_s"] for conversacion in conversaciones]), 1),
        "tiempo_max_s": round(max((conversacion["total_s"] for conversacion in conversaciones), default=0), 1),
        "prompt_tokens_max": max(
            (vuelta["prompt_tokens"] or 0 for conversacion in conversaciones for vuelta in conversacion["vueltas"]),
            default=0,
        ),
    }


def resumen() -> None:
    salida: dict = {"condiciones": {}}

    # ¿Dicen los marcadores algo de la legibilidad? Se mira en el corpus, contra
    # la lectura a mano: si no bajan al subir la legibilidad, no sirven.
    lectura = {
        fila["id"]: fila for fila in json.loads((CARPETA / "lectura.json").read_text(encoding="utf-8"))["lecturas"]
    }
    por_nivel: dict[int, list[int]] = {}
    for conversacion in json.loads(CORPUS.read_text(encoding="utf-8"))["conversaciones"]:
        if conversacion["id"] in lectura:
            # La validada por el autor si la hay; si no, la del borrador.
            nivel = (lectura[conversacion["id"]].get("validada") or lectura[conversacion["id"]])["legibilidad"]
            por_nivel.setdefault(nivel, []).append(sum(_marcadores(conversacion["respuesta"]).values()))
    salida["marcadores_frente_a_la_lectura"] = {
        nivel: {"respuestas": len(valores), "marcadores_mediana": _mediana(valores)}
        for nivel, valores in sorted(por_nivel.items())
    }
    print("== marcadores frente a la legibilidad leída a mano (corpus)")
    for nivel, cifras in salida["marcadores_frente_a_la_lectura"].items():
        print(f"  legibilidad {nivel}: {cifras['respuestas']} respuestas · mediana de marcadores {cifras['marcadores_mediana']}")

    print("\n== la comparación")
    for ruta in sorted(CARPETA.glob("comparacion-*.json")):
        registro = json.loads(ruta.read_text(encoding="utf-8"))
        nombre = registro["condiciones"]["condicion"]["nombre"]
        cifras = _resumen_de(registro["conversaciones"])
        for juez in sorted(CARPETA.glob(f"juez-*-{ruta.stem}.json")):
            juicios = [
                fila
                for fila in json.loads(juez.read_text(encoding="utf-8"))["juicios"]
                if not fila["error"] and fila.get("json_valido")
            ]
            cifras[f"juez {juez.stem.removeprefix('juez-').removesuffix('-' + ruta.stem)}"] = {
                "juzgadas": len(juicios),
                "infieles": sum(not fila["fiel_recalculado"] for fila in juicios),
                "legibilidad": dict(sorted(Counter(fila["juicio"]["legibilidad"] for fila in juicios).items())),
            }
        salida["condiciones"][nombre] = cifras
        print(f"  {nombre}: {json.dumps(cifras, ensure_ascii=False)}")
    _guardar(salida, CARPETA / "resumen.json")
    print(f"\nEl resumen, en {CARPETA / 'resumen.json'}")


# ----- 5 · La calibración -----


def validar(carpeta: Path) -> None:
    """Lleva a `lectura.json` lo validado por el autor en la página de validación.

    La página guarda cada decisión en su base de datos, fuera del repositorio;
    se exporta a una carpeta (un JSON por caso) y aquí se copia a `validada`,
    junto a la lectura de Claude que se validaba. Sin esto, la referencia de la
    calibración no estaría en el repositorio y no se podría citar.
    """
    ruta = CARPETA / "lectura.json"
    registro = json.loads(ruta.read_text(encoding="utf-8"))
    validaciones = {}
    for fichero in sorted(carpeta.glob("*.json")):
        cuerpo = json.loads(fichero.read_text(encoding="utf-8"))
        validaciones[cuerpo["id"]] = {
            clave: cuerpo.get(clave) for clave in ("fiel", "legibilidad", "decision", "nota", "actualizada")
        }
    desconocidas = set(validaciones) - {lectura["id"] for lectura in registro["lecturas"]}
    if desconocidas:
        sys.exit(f"ABORTADO: validaciones de casos que no están en la lectura: {sorted(desconocidas)}")
    for lectura in registro["lecturas"]:
        lectura["validada"] = validaciones.get(lectura["id"])
    registro["condiciones"]["validacion"] = {
        "validadas": len(validaciones),
        "exportada": datetime.now().astimezone().isoformat(timespec="seconds"),
        "origen": "la página de validación de #192 (artefacto privado), colección `validaciones`",
    }
    _guardar(registro, ruta)
    decisiones = Counter(validacion["decision"] for validacion in validaciones.values())
    print(f"  {len(validaciones)} de {len(registro['lecturas'])} validadas · {dict(decisiones)} → {ruta}")


def _kappa(referencia: list[bool], dicho: list[bool]) -> float | None:
    """El kappa de Cohen: el acuerdo, descontado el que saldría por azar."""
    if not referencia:
        return None
    total = len(referencia)
    observado = sum(uno == otro for uno, otro in zip(referencia, dicho, strict=True)) / total
    por_azar = sum(
        (referencia.count(valor) / total) * (dicho.count(valor) / total) for valor in (True, False)
    )
    return round((observado - por_azar) / (1 - por_azar), 3) if por_azar < 1 else None


def _frente_a(referencia: dict[str, dict], dicho: dict[str, dict]) -> dict:
    """Un juez (o la lectura, o una combinación) frente a lo validado.

    «Positivo» es INFIEL: lo que importa es cuántas infieles caza y cuántas
    fieles da por infieles.
    """
    comunes = [clave for clave in referencia if clave in dicho]
    ref_fiel = [referencia[clave]["fiel"] for clave in comunes]
    dicho_fiel = [dicho[clave]["fiel"] for clave in comunes]
    infieles = [clave for clave in comunes if not referencia[clave]["fiel"]]
    fieles = [clave for clave in comunes if referencia[clave]["fiel"]]
    escapadas = [clave for clave in infieles if dicho[clave]["fiel"]]
    falsas = [clave for clave in fieles if not dicho[clave]["fiel"]]
    con_legibilidad = [clave for clave in comunes if dicho[clave].get("legibilidad") is not None]
    diferencias = [dicho[clave]["legibilidad"] - referencia[clave]["legibilidad"] for clave in con_legibilidad]
    return {
        "casos": len(comunes),
        "acuerdo": sum(uno == otro for uno, otro in zip(ref_fiel, dicho_fiel, strict=True)),
        "kappa": _kappa(ref_fiel, dicho_fiel),
        "infieles": len(infieles),
        "cazadas": len(infieles) - len(escapadas),
        "fieles": len(fieles),
        "falsas_alarmas": len(falsas),
        "escapadas_ids": escapadas,
        "falsas_alarmas_ids": falsas,
        "legibilidad_igual": sum(diferencia == 0 for diferencia in diferencias) if diferencias else None,
        "legibilidad_diferencia_media": round(statistics.mean(diferencias), 2) if diferencias else None,
    }


def calibrar() -> None:
    """Cada juez, y la lectura de Claude, frente a lo validado por el autor."""
    lecturas = json.loads((CARPETA / "lectura.json").read_text(encoding="utf-8"))["lecturas"]
    referencia = {lectura["id"]: lectura["validada"] for lectura in lecturas if lectura.get("validada")}
    print(f"== referencia: {len(referencia)} casos validados por el autor")
    dichos: dict[str, dict[str, dict]] = {
        "lectura de Claude": {lectura["id"]: lectura for lectura in lecturas},
    }
    for ruta in sorted(CARPETA.glob("juez-*.json")):
        registro = json.loads(ruta.read_text(encoding="utf-8"))
        if "juzgado" in registro["condiciones"]:
            continue  # los juicios de la comparación no se calibran: no hay lectura a mano
        dichos[registro["condiciones"]["juez"]] = {
            fila["id"]: {"fiel": fila["fiel_recalculado"], "legibilidad": fila["juicio"]["legibilidad"]}
            for fila in registro["juicios"]
            if not fila["error"] and fila.get("json_valido")
        }
    # Dos jueces juntos: infiel si lo dice alguno (caza más) o si lo dicen los
    # dos (menos falsas alarmas). La legibilidad no se combina.
    jueces = [nombre for nombre in dichos if nombre != "lectura de Claude"]
    for posicion, uno in enumerate(jueces):
        for otro in jueces[posicion + 1 :]:
            comunes = set(dichos[uno]) & set(dichos[otro])
            dichos[f"{uno} o {otro}"] = {
                clave: {"fiel": dichos[uno][clave]["fiel"] and dichos[otro][clave]["fiel"]} for clave in comunes
            }
            dichos[f"{uno} y {otro}"] = {
                clave: {"fiel": dichos[uno][clave]["fiel"] or dichos[otro][clave]["fiel"]} for clave in comunes
            }

    salida = {"validados": len(referencia), "frente_a_la_referencia": {}}
    for nombre, dicho in dichos.items():
        cifras = _frente_a(referencia, dicho)
        salida["frente_a_la_referencia"][nombre] = cifras
        print(
            f"  {nombre:32} {cifras['casos']:3} casos · acuerdo {cifras['acuerdo']}/{cifras['casos']} "
            f"(kappa {cifras['kappa']}) · infieles cazadas {cifras['cazadas']}/{cifras['infieles']} · "
            f"falsas alarmas {cifras['falsas_alarmas']}/{cifras['fieles']}"
            + (
                f" · legibilidad igual {cifras['legibilidad_igual']}, diferencia media {cifras['legibilidad_diferencia_media']:+}"
                if cifras["legibilidad_igual"] is not None
                else ""
            )
        )
        if cifras["escapadas_ids"]:
            print(f"      se le escapan: {cifras['escapadas_ids']}")
    _guardar(salida, CARPETA / "calibracion.json")
    print(f"\nLa calibración, en {CARPETA / 'calibracion.json'}")


# ----- 6 · La ventana -----

VENTANAS = (8192, 16384)
# Las dos vueltas que más ocuparon en la comparación: las fichas de los modelos
# (el resultado más largo) y encadenar una noticia (la vuelta con más salida).
CONSULTAS_PESADAS = ("otro_dominio-3", "bucle-encadena-nyt")
# El tope del historial de producción (`chat_max_history_chars`, #189).
HISTORIAL_MAXIMO = 4000


def _historial_maximo() -> list[dict]:
    """Turnos reales —preguntas y respuestas de `05-llano` en la comparación— hasta
    el tope de caracteres que admite la API, como lo recortaría la interfaz."""
    conversaciones = json.loads((CARPETA / "comparacion-C-05.json").read_text(encoding="utf-8"))["conversaciones"]
    historial: list[dict] = []
    caracteres = 0
    for conversacion in conversaciones:
        pareja = [
            {"role": "user", "content": conversacion["consulta"]},
            {"role": "assistant", "content": conversacion["respuesta"]},
        ]
        tamano = sum(len(turno["content"]) for turno in pareja)
        if caracteres + tamano > HISTORIAL_MAXIMO:
            break
        historial += pareja
        caracteres += tamano
    return historial


def _argumentos_ventana(argumentos: list[str]) -> tuple[tuple[int, ...], int, tuple[str, ...]]:
    """`[--ctx 8192,16384] [--veces N] [consulta ...]`. Sin nada, la primera medida."""
    ventanas, veces, elegidas = VENTANAS, 1, []
    pendientes = iter(argumentos)
    for argumento in pendientes:
        if argumento == "--ctx":
            ventanas = tuple(int(valor) for valor in next(pendientes).split(","))
        elif argumento == "--veces":
            veces = int(next(pendientes))
        else:
            elegidas.append(argumento)
    return ventanas, veces, tuple(elegidas) or CONSULTAS_PESADAS


def _ruta_ventana(ventanas: tuple[int, ...], veces: int, elegidas: tuple[str, ...]) -> Path:
    """`ventana.json` para la primera medida; las repeticiones, en otro fichero."""
    if (ventanas, veces, elegidas) == (VENTANAS, 1, CONSULTAS_PESADAS):
        return CARPETA / "ventana.json"
    return CARPETA / f"ventana-{'-'.join(elegidas)}-{'-'.join(map(str, ventanas))}-x{veces}.json"


async def ventana(ventanas: tuple[int, ...], veces: int, elegidas: tuple[str, ...]) -> None:
    """Cuánto cuesta subir `num_ctx` de 8.192 a 16.384, y si con 8.192 se recorta.

    La comparación de #192 enseñó que la regla de #189 medía sólo el prompt: el
    razonamiento y la respuesta también ocupan ventana, y la vuelta de las fichas
    con `05-llano` llegó a 7.575 tokens SIN historial. Aquí las dos vueltas más
    pesadas, con el historial máximo, en las dos ventanas: si con 8.192 el
    prompt sale más corto que con 16.384 para la misma entrada, Ollama lo
    recortó. Y la memoria de cada una, de `api/ps`, sin sondear `nvidia-smi`.

    Con la configuración de producción desde #192: `05-llano` y el perfil
    preciso, que es lo que manda el agente.

    Con argumentos, repite las consultas elegidas en las ventanas elegidas. Se
    añadió tras la primera medida, que dio un `empty_answer` con 16.384 sin
    llenar la ventana y no guardaba con qué explicarlo: desde entonces cada
    medida guarda los pasos enteros de la traza y lo que devolvió Ollama en
    cada vuelta, razonamiento incluido.
    """
    fuente = Fuente("ventana", "qwen3.5:27b", "05-llano", think=True)
    historial = _historial_maximo()
    caracteres = sum(len(turno["content"]) for turno in historial)
    registro: dict = {
        "condiciones": await _condiciones({fuente.modelo})
        | {
            "prompt": fuente.prompt,
            "prompt_huella": _huella(prompts.cargar(fuente.prompt)),
            "decimales": 3,
            "muestreo": PERFIL_PRECISO,
            "historial": {"turnos": len(historial), "caracteres": caracteres},
            "ventanas": ventanas,
            "consultas": elegidas,
            "veces": veces,
        },
        "medidas": [],
    }
    print(f"  historial: {len(historial)} turnos, {caracteres} caracteres")
    consultas = {clave: (consulta, esperadas) for clave, _, consulta, _, esperadas in _consultas()}
    ruta = _ruta_ventana(ventanas, veces, elegidas)
    async with httpx.AsyncClient(timeout=10.0) as cliente:
        for num_ctx in ventanas:
            print(f"\n== num_ctx {num_ctx}")
            for clave in elegidas:
                for vez in range(1, veces + 1):
                    await _medir_ventana(cliente, registro, ruta, fuente, historial, num_ctx, clave, vez, consultas[clave][0])
    print(f"\nLas medidas, en {ruta}")


async def _medir_ventana(
    cliente: httpx.AsyncClient,
    registro: dict,
    ruta: Path,
    fuente: Fuente,
    historial: list[dict],
    num_ctx: int,
    clave: str,
    vez: int,
    consulta: str,
) -> None:
    config = _config(fuente, 3, PERFIL_PRECISO, num_ctx, clase=OllamaQueGuardaElRazonamiento)
    resultado = await responder(consulta, historial, config)
    crudo = config.backend.crudo if isinstance(config.backend, OllamaQueGuardaElRazonamiento) else []
    cargado = await _pedir(cliente, "GET", "api/ps") or {}
    memoria = next((entrada for entrada in cargado.get("models", []) if entrada.get("name") == fuente.modelo), {})
    vueltas = [paso["metrics"] for paso in resultado["steps"] if paso["kind"] == "model"]
    medida = {
        "num_ctx": num_ctx,
        "consulta": clave,
        "vez": vez,
        "estado": resultado["status"],
        "total_s": resultado["total_s"],
        "vueltas": [
            {
                "prompt_tokens": vuelta["prompt_tokens"],
                "output_tokens": vuelta["output_tokens"],
                "load_s": vuelta["load_s"],
                "total_s": vuelta["total_s"],
            }
            for vuelta in vueltas
        ],
        "ocupacion_max": max(
            ((vuelta["prompt_tokens"] or 0) + (vuelta["output_tokens"] or 0) for vuelta in vueltas), default=0
        ),
        "vram_mib": round((memoria.get("size_vram") or 0) / 2**20),
        "tamano_mib": round((memoria.get("size") or 0) / 2**20),
        "respuesta": resultado["answer"],
        "pasos": resultado["steps"],
        "ollama": crudo,
    }
    registro["medidas"].append(medida)
    _guardar(registro, ruta)
    herramientas = [paso["name"] for paso in resultado["steps"] if paso["kind"] == "tool"]
    print(
        f"  {clave:22} #{vez} {medida['estado']:12} {medida['total_s']:6.1f} s · "
        f"prompt por vuelta {[vuelta['prompt_tokens'] for vuelta in medida['vueltas']]} · "
        f"ocupación máx {medida['ocupacion_max']} de {num_ctx} · VRAM {medida['vram_mib']} MiB · "
        f"fin {[vuelta['done_reason'] for vuelta in crudo]} · herramientas {herramientas}"
    )


async def _con_mcp(corrutina) -> None:
    """Sirve el `mcp` de producción en proceso mientras corre `corrutina`."""
    app = SERVIDOR.streamable_http_app()
    # El gestor de sesiones de FastMCP arranca en el lifespan, que
    # ASGITransport no ejecuta: se entra a mano (como en los tests).
    async with app.router.lifespan_context(app):
        mcp_session._http_client = lambda corte: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE, timeout=corte
        )
        await corrutina


async def main(parte: str, argumentos: list[str]) -> None:
    print("== condiciones")
    if parte == "jueces":
        modelo = argumentos[0]
        juzgado = CARPETA / argumentos[1] if len(argumentos) > 1 else CORPUS
        sufijo = "" if juzgado == CORPUS else f"-{juzgado.stem}"
        ruta = Path(os.environ.get("FIDELIDAD_JSON", CARPETA / f"juez-{modelo.replace(':', '-')}{sufijo}.json"))
        await jueces(modelo, ruta, juzgado)
        print(f"\nTodos los juicios, con el razonamiento de cada uno: {ruta}")
        return
    if parte == "comparar":
        await _con_mcp(comparar([_condicion(nombre) for nombre in argumentos]))
        return
    if parte == "resumen":
        resumen()
        return
    if parte == "validar":
        validar(Path(argumentos[0]))
        return
    if parte == "calibrar":
        calibrar()
        return
    if parte == "ventana":
        await _con_mcp(ventana(*_argumentos_ventana(argumentos)))
        return

    fuentes = [fuente for fuente in FUENTES if fuente.nombre in argumentos]
    ruta = Path(os.environ.get("FIDELIDAD_JSON", CORPUS))
    registro: dict = {"condiciones": await _condiciones_del_corpus(fuentes)}
    for clave, valor in registro["condiciones"].items():
        print(f"  {clave}: {valor}")
    await _con_mcp(corpus(registro, fuentes, ruta))
    _guardar(registro, ruta)
    print(f"\nTodo lo generado, con las respuestas y las trazas enteras: {ruta}")


if __name__ == "__main__":
    parte, argumentos = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    if parte == "jueces":
        if len(argumentos) not in (1, 2):
            sys.exit("Uso: fidelidad.py jueces <modelo> [fichero]. Un juez por ejecución.")
    elif parte == "corpus":
        existentes = [fuente.nombre for fuente in FUENTES]
        argumentos = argumentos or existentes
        desconocidas = [nombre for nombre in argumentos if nombre not in existentes]
        if desconocidas:
            sys.exit(f"Fuentes desconocidas: {desconocidas}. Hay: {existentes}")
    elif parte == "comparar":
        if not argumentos:
            sys.exit("Uso: fidelidad.py comparar A B C D | fidelidad.py comparar E:<prompt>")
    elif parte == "validar":
        if len(argumentos) != 1:
            sys.exit("Uso: fidelidad.py validar <carpeta con la exportación de la página>")
    elif parte == "ventana":
        try:
            _, _, elegidas = _argumentos_ventana(argumentos)
        except (StopIteration, ValueError):
            sys.exit("Uso: fidelidad.py ventana [--ctx 8192,16384] [--veces N] [consulta ...]")
        existentes = {clave for clave, *_ in _consultas()}
        if desconocidas := [clave for clave in elegidas if clave not in existentes]:
            sys.exit(f"Consultas desconocidas: {desconocidas}. Hay: {sorted(existentes)}")
    elif parte not in ("resumen", "calibrar"):
        sys.exit(
            "Uso: fidelidad.py corpus | jueces <modelo> [fichero] | comparar <condición ...>"
            " | resumen | validar <carpeta> | calibrar | ventana [--ctx N,N] [--veces N] [consulta ...]"
        )
    asyncio.run(main(parte, argumentos))
