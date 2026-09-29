"""#192 (2026-09-29) - La fidelidad de las respuestas del agente.

La pregunta de #192 es si lo que el agente CUENTA está en lo que devolvieron
las herramientas, y qué prompt lo consigue sin sonar técnico. Se responde por
partes; ésta es la primera:

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
manda también es una condición—, el guion lee esos parámetros de Ollama y los
guarda con lo demás.

El servidor MCP es el `mcp` de `backend.main`, servido en proceso como en
`agente_a40.py`: las herramientas se ejecutan de verdad, con NLP_BACKEND=local,
y las de noticias llaman a NYT y a Guardian.

Ejecutar desde la raíz, con el túnel abierto (la sesión la abre
`spikes/fidelidad_a40.sh`):

    NLP_BACKEND=local .venv/bin/python spikes/fidelidad.py corpus [fuente ...]

Sin fuentes, las cuatro. `OLLAMA_URL` cambia el servidor (defecto
`http://127.0.0.1:11500`) y `FIDELIDAD_JSON` el fichero donde se guarda
(defecto `spikes/fidelidad/corpus.json`).
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
SALIDA = Path(os.environ.get("FIDELIDAD_JSON", RAIZ / "spikes" / "fidelidad" / "corpus.json"))

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


def _guardar(registro: dict) -> None:
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(
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


async def _condiciones(fuentes: list[Fuente]) -> dict:
    """Lo que hace falta para situar y repetir la medida, con lo que el agente NO manda."""
    async with httpx.AsyncClient(timeout=10.0) as cliente:
        version = await _pedir(cliente, "GET", "api/version") or {}
        etiquetas = await _pedir(cliente, "GET", "api/tags") or {}
        modelos = {}
        for modelo in sorted({fuente.modelo for fuente in fuentes}):
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
                # La temperatura y el resto del muestreo: el agente no los manda.
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
        "num_ctx": NUM_CTX,
        "keep_alive": KEEP_ALIVE,
        "nlp_backend": settings.nlp_backend,
        "modelos": modelos,
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


async def corpus(registro: dict, fuentes: list[Fuente]) -> None:
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
            _guardar(registro)
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


PARTES = {"corpus": corpus}


async def main(parte: str, fuentes: list[Fuente]) -> None:
    print("== condiciones")
    registro: dict = {"condiciones": await _condiciones(fuentes)}
    for clave, valor in registro["condiciones"].items():
        print(f"  {clave}: {valor}")

    app = SERVIDOR.streamable_http_app()
    # El gestor de sesiones de FastMCP arranca en el lifespan, que
    # ASGITransport no ejecuta: se entra a mano (como en los tests).
    async with app.router.lifespan_context(app):
        mcp_session._http_client = lambda corte: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE, timeout=corte
        )
        await PARTES[parte](registro, fuentes)

    _guardar(registro)
    print(f"\nTodo lo generado, con las respuestas y las trazas enteras: {SALIDA}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in PARTES:
        sys.exit(f"Uso: fidelidad.py <parte> [fuente ...]. Partes: {list(PARTES)}")
    pedidas = sys.argv[2:] or [fuente.nombre for fuente in FUENTES]
    existentes = [fuente.nombre for fuente in FUENTES]
    desconocidas = [nombre for nombre in pedidas if nombre not in existentes]
    if desconocidas:
        sys.exit(f"Fuentes desconocidas: {desconocidas}. Hay: {existentes}")
    asyncio.run(main(sys.argv[1], [fuente for fuente in FUENTES if fuente.nombre in pedidas]))
