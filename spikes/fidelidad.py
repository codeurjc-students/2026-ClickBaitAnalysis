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
   pedido, se para ahí en vez de gastar la sesión.

Ejecutar desde la raíz, con el túnel abierto (la sesión la abre
`spikes/fidelidad_a40.sh`):

    NLP_BACKEND=local .venv/bin/python spikes/fidelidad.py corpus [fuente ...]
    .venv/bin/python spikes/fidelidad.py jueces <modelo>

Sin fuentes, las cuatro; los jueces, de uno en uno. `OLLAMA_URL` cambia el
servidor (defecto `http://127.0.0.1:11500`) y `FIDELIDAD_JSON` el fichero donde
se guarda (defecto `spikes/fidelidad/corpus.json` y
`spikes/fidelidad/juez-<modelo>.json`).
"""

import asyncio
import hashlib
import json
import logging
import os
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
from spikes.tool_calling_fase2 import PRUEBAS  # noqa: E402

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


def _consultas() -> list[tuple[str, str, str, list]]:
    """Las 27 consultas, como (clave, categoría, consulta, historial).

    La clave es estable —la categoría y su número de orden, o el nombre del
    bucle— para que la lectura a mano y los jueces se refieran a lo mismo.
    """
    filas = [(categoria, consulta) for categoria, consulta, _ in PRUEBAS if categoria != "SIN_TOOL"]
    filas += [("CONTRASTE", consulta) for _, consulta, _ in CONTRASTE]
    numero = Counter()
    consultas = []
    for categoria, consulta in filas:
        numero[categoria] += 1
        consultas.append((f"{categoria.lower()}-{numero[categoria]}", categoria, consulta, []))
    consultas += [
        (f"bucle-{nombre}", "BUCLE", consulta, historial) for nombre, consulta, historial in BUCLES
    ]
    return consultas


def _config(fuente: Fuente) -> Configuracion:
    """La configuración del agente de producción, con el modelo, el prompt y el `think` de la fuente."""
    return Configuracion(
        backend=OllamaClient(
            URL, fuente.modelo, num_ctx=NUM_CTX, keep_alive=KEEP_ALIVE, timeout=LLM_TIMEOUT
        ),
        servers=[_SERVIDOR_URL],
        prompt=prompts.cargar(fuente.prompt),
        discovery_timeout=10.0,
        # Las señales locales cargan su modelo la primera vez que se usan.
        execute_timeout=120.0,
        think=fuente.think,
    )


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
        for clave, categoria, consulta, historial in elegidas:
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


async def jueces(modelo: str, ruta: Path) -> None:
    """Un juez sobre el corpus, en una o varias sesiones.

    Juzgar es lento —el juez razona y escribe cada afirmación—, así que un juez
    puede no caber en una sesión corta de GPU. Si ya hay un fichero de este
    juez con las mismas condiciones fijas, se continúa: se conservan los
    juicios hechos (también los de JSON no válido, que son un resultado) y se
    repiten sólo los que fallaron por error. Cada sesión queda anotada.
    """
    corpus_leido = json.loads(CORPUS.read_text(encoding="utf-8"))
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
        "corpus": hashlib.sha256(CORPUS.read_bytes()).hexdigest()[:12],
        "corpus_generado": corpus_leido["condiciones"]["fecha"],
    }
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


async def main(parte: str, argumentos: list[str]) -> None:
    print("== condiciones")
    if parte == "jueces":
        modelo = argumentos[0]
        ruta = Path(os.environ.get("FIDELIDAD_JSON", CARPETA / f"juez-{modelo.replace(':', '-')}.json"))
        await jueces(modelo, ruta)
        print(f"\nTodos los juicios, con el razonamiento de cada uno: {ruta}")
        return

    fuentes = [fuente for fuente in FUENTES if fuente.nombre in argumentos]
    ruta = Path(os.environ.get("FIDELIDAD_JSON", CORPUS))
    registro: dict = {"condiciones": await _condiciones_del_corpus(fuentes)}
    for clave, valor in registro["condiciones"].items():
        print(f"  {clave}: {valor}")

    app = SERVIDOR.streamable_http_app()
    # El gestor de sesiones de FastMCP arranca en el lifespan, que
    # ASGITransport no ejecuta: se entra a mano (como en los tests).
    async with app.router.lifespan_context(app):
        mcp_session._http_client = lambda corte: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE, timeout=corte
        )
        await corpus(registro, fuentes, ruta)

    _guardar(registro, ruta)
    print(f"\nTodo lo generado, con las respuestas y las trazas enteras: {ruta}")


if __name__ == "__main__":
    parte, argumentos = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    if parte == "jueces":
        if len(argumentos) != 1:
            sys.exit("Uso: fidelidad.py jueces <modelo>. Un juez por ejecución.")
    elif parte == "corpus":
        existentes = [fuente.nombre for fuente in FUENTES]
        argumentos = argumentos or existentes
        desconocidas = [nombre for nombre in argumentos if nombre not in existentes]
        if desconocidas:
            sys.exit(f"Fuentes desconocidas: {desconocidas}. Hay: {existentes}")
    else:
        sys.exit("Uso: fidelidad.py corpus [fuente ...] | fidelidad.py jueces <modelo>")
    asyncio.run(main(parte, argumentos))
