"""#188 (2026-09-26) - El agente real, contra la A40.

Hasta aquí, lo medido con el modelo eran guiones del spike que hablaban con
Ollama a mano (fases 1–5, PR #176). Esto pasa las mismas preguntas por
`backend/agent/agente.py`, el código que servirá la API, y mide lo que #188
dejó por decidir:

1. `contexto`: qué cuenta `prompt_tokens` —la misma conversación dos veces
   seguidas— y cuánto cuestan el catálogo y el prompt. El catálogo es el real,
   con las 12 herramientas de `backend.main`: la A40 midió 11, porque la fase 5
   montaba su servidor sin `analyze_headline`.
2. `seleccion`: las 20 consultas de la fase 5 y las 6 de contraste, cortadas en
   la primera decisión (`max_rounds=1`), con `think` en tres condiciones: sin el
   campo, como lo mandaban los guiones del spike; `false`; y `true`. En las
   genéricas («¿es clickbait?») cuenta como acierto también `analyze_headline`,
   que el criterio de la fase 2 no conocía.
3. `bucles`: consultas completas de punta a punta, con `think=false` y los
   resultados enteros. Las que devuelven más de 1.500 caracteres se repiten
   recortando a esa cifra, que es la del spike, y tres se repiten con
   `think=true`.

Esas tres son la primera sesión (2026-09-26, 08:41), sobre el agente del commit
`a414899`. De ella salió que sin razonar el modelo se inventa los resultados, y
el agente pasó a razonar por defecto y a enviar las descripciones sin sangría.
La cuarta parte mide eso, la configuración que se queda:

4. `definitiva`: el contexto otra vez —cuánto ahorra quitar la sangría—, las 26
   consultas razonando, y los seis bucles razonando con los resultados enteros.

Y una quinta, de #197 (2026-09-26), sobre el cuerpo que se escribe «None»:

5. `cuerpo`: las cuatro consultas genéricas y la del análisis completo —ninguna
   trae cuerpo—, tres veces cada una y cortadas en la primera decisión,
   anotando qué `content` manda el modelo a `analyze_headline` y cómo queda la
   incoherencia. Desde entonces, la selección guarda además los argumentos de
   cada llamada, que antes no guardaba y por eso no se pudo contar desde aquí.

El servidor MCP es el `mcp` de `backend.main` —el mismo objeto que arranca en
producción— servido en proceso, como en la fase 5: las herramientas se ejecutan
aquí de verdad, con NLP_BACKEND=local, y las de noticias llaman a NYT y a
Guardian. El modelo, por el túnel propio hacia la A40.

Ejecutar desde la raíz, con el túnel abierto (la sesión la abre
`spikes/agente_a40.sh`):

    NLP_BACKEND=local .venv/bin/python spikes/agente_a40.py [contexto] [seleccion] [bucles]

Sin partes, las tres primeras. `OLLAMA_URL` cambia el servidor (defecto
`http://127.0.0.1:11500`), `OLLAMA_MODELO` el modelo (defecto `qwen3.5:27b`), y
`AGENTE_A40_JSON` el fichero donde se guarda todo lo medido, con las respuestas
enteras para leerlas.
"""

import asyncio
import json
import logging
import os
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx
import structlog

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Los guiones del spike leen `sys.argv` AL IMPORTARSE (modelo y `num_ctx`), y
# con las partes de éste en la línea de órdenes fallarían. Se importan con la
# línea vacía y se devuelve después.
_ARGUMENTOS, sys.argv = sys.argv, sys.argv[:1]
from backend.agent import agente, prompts  # noqa: E402
from backend.agent.agente import Configuracion, responder  # noqa: E402
from backend.core.mcp import session as mcp_session  # noqa: E402
from backend.integrations.llm.ollama import OllamaClient  # noqa: E402
from backend.main import mcp as SERVIDOR  # noqa: E402
from spikes.tool_calling_descripciones_contraste import (  # noqa: E402
    CONSULTAS as CONTRASTE,
)
from spikes.tool_calling_fase2 import CLICKBAIT_CUALQUIERA, PRUEBAS  # noqa: E402
from spikes.tool_calling_fase3 import CONSULTAS as CONSULTAS_FASE3  # noqa: E402

sys.argv = _ARGUMENTOS

# Sólo avisos: los eventos `agent.*` de cada paso ya van en lo que se imprime.
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
for ruidoso in ("httpx", "mcp", "backend"):
    logging.getLogger(ruidoso).setLevel(logging.WARNING)

URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11500")
MODELO = os.environ.get("OLLAMA_MODELO", "qwen3.5:27b")
NUM_CTX = 8192
PROMPT = "04-preciso"
RECORTE = 1500  # lo que cortaba el spike (`tool_calling_fase3.py`)
SALIDA = Path(os.environ.get("AGENTE_A40_JSON", "/tmp/agente_a40.json"))

_BASE = "http://127.0.0.1:8765"
_SERVIDOR_URL = f"{_BASE}/mcp"

# `None` es no mandar el campo: lo que hacían los guiones del spike.
CONDICIONES_THINK = {"sin campo": None, "false": False, "true": True}

GENERICA_ACEPTABLE = CLICKBAIT_CUALQUIERA | {"analyze_headline"}

BUCLES = [
    ("encadena-nyt", CONSULTAS_FASE3[0], []),
    ("dos-senales", CONSULTAS_FASE3[1], []),
    (
        "analisis-completo",
        "Analiza a fondo el titular 'You Won't Believe What This Dog Did Next' "
        "con todas las señales del sistema.",
        [],
    ),
    (
        "incoherencia",
        "¿El titular 'Miracle Cure Discovered' encaja con el texto 'A small trial "
        "found modest effects in mice after eight weeks'?",
        [],
    ),
    (
        "encadena-guardian",
        "Busca en The Guardian una noticia sobre el clima y dime si su titular es "
        "clickbait.",
        [],
    ),
    (
        "segundo-turno",
        "¿Y qué dice el modelo de caja negra?",
        [
            {"role": "user", "content": "¿Es clickbait 'Scientists Discover New Species'?"},
            {
                "role": "assistant",
                "content": "El detector léxico no encontró ninguna pista en el titular.",
            },
        ],
    ),
]
BUCLES_CON_THINK = ("dos-senales", "analisis-completo", "incoherencia")


class OllamaComoElSpike(OllamaClient):
    """El cliente real, sin el campo `think`: como lo mandaban los guiones del spike."""

    async def make_request(self, endpoint, method, params=None, json=None):
        if json is not None:
            json = {clave: valor for clave, valor in json.items() if clave != "think"}
        return await super().make_request(endpoint, method, params=params, json=json)


def _config(think: bool | None, **cambios) -> Configuracion:
    clase = OllamaComoElSpike if think is None else OllamaClient
    return Configuracion(
        backend=clase(URL, MODELO, num_ctx=NUM_CTX, keep_alive="10m", timeout=300.0),
        servers=[_SERVIDOR_URL],
        prompt=prompts.cargar(PROMPT),
        discovery_timeout=10.0,
        # Las señales locales cargan su modelo la primera vez que se usan.
        execute_timeout=120.0,
        think=bool(think),
        **cambios,
    )


def _guardar(registro: dict) -> None:
    SALIDA.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")


def _mediana(valores: list[float]) -> float:
    return statistics.median(valores) if valores else float("nan")


# ----- 1 · Qué cuenta `prompt_tokens` y cuánto cuesta el catálogo -----


async def contexto(registro: dict) -> None:
    config = _config(False)
    catalogo = await agente._descubrir(config)
    herramientas = [herramienta for herramienta, _ in catalogo.values()]
    sistema = {"role": "system", "content": config.prompt}
    usuario = {"role": "user", "content": "¿Es clickbait 'You Won't Believe What Happened Next'?"}

    # El orden importa: cada petición cambia el PRINCIPIO de la anterior salvo la
    # segunda, que es idéntica. Si Ollama reutiliza lo ya evaluado, sólo esa
    # debería contar menos.
    peticiones = [
        ("con catálogo", [sistema, usuario], herramientas),
        ("con catálogo, idéntica", [sistema, usuario], herramientas),
        ("sin catálogo", [sistema, usuario], []),
        ("sólo la consulta", [usuario], []),
        ("con catálogo, otra vez", [sistema, usuario], herramientas),
    ]
    medidas = {}
    print("\n== contexto: qué cuenta `prompt_tokens`")
    print(f"  {len(herramientas)} herramientas: {', '.join(sorted(catalogo))}")
    for nombre, mensajes, catalogo_enviado in peticiones:
        respuesta = (await config.backend.chat(mensajes, catalogo_enviado)).unwrap()
        metricas = respuesta["metrics"]
        medidas[nombre] = metricas
        print(
            f"  {nombre:24} prompt_tokens {metricas['prompt_tokens']!s:>5} · "
            f"salida {metricas['output_tokens']!s:>4} · carga {metricas['load_s']:.2f} s · "
            f"total {metricas['total_s']:.2f} s"
        )

    catalogo_tokens = medidas["con catálogo"]["prompt_tokens"] - medidas["sin catálogo"]["prompt_tokens"]
    prompt_tokens = medidas["sin catálogo"]["prompt_tokens"] - medidas["sólo la consulta"]["prompt_tokens"]
    print(f"  => el catálogo de {len(herramientas)} herramientas: {catalogo_tokens} tokens")
    print(f"  => el prompt `{PROMPT}`: {prompt_tokens} tokens")
    registro["contexto"] = {
        "herramientas": sorted(catalogo),
        "medidas": medidas,
        "catalogo_tokens": catalogo_tokens,
        "prompt_tokens": prompt_tokens,
    }
    _guardar(registro)


# ----- 2 · Selección, con `think` en tres condiciones -----


async def seleccion(registro: dict, condiciones: dict | None = None) -> None:
    condiciones = CONDICIONES_THINK if condiciones is None else condiciones
    pruebas = [
        (categoria, consulta, GENERICA_ACEPTABLE if categoria == "GENERICA" else aceptables)
        for categoria, consulta, aceptables in PRUEBAS
    ] + [("CONTRASTE", consulta, aceptables) for _, consulta, aceptables in CONTRASTE]

    registro["seleccion"] = {}
    for etiqueta, think in condiciones.items():
        print(f"\n== selección, think {etiqueta}: {len(pruebas)} consultas, max_rounds=1")
        filas = []
        for categoria, consulta, aceptables in pruebas:
            resultado = await responder(consulta, [], _config(think, max_rounds=1))
            vuelta = next((paso for paso in resultado["steps"] if paso["kind"] == "model"), None)
            pedidas = set(vuelta["tool_calls"]) if vuelta else set()
            acierto = (not pedidas) if not aceptables else bool(pedidas & aceptables)
            argumentos_mal = sum(
                1
                for paso in resultado["steps"]
                if paso["kind"] == "tool"
                and (paso["error"] or "").startswith("Los argumentos no encajan")
            )
            fila = {
                "categoria": categoria,
                "consulta": consulta,
                "pedidas": sorted(pedidas),
                "acierto": acierto,
                "estado": resultado["status"],
                "detalle": resultado["detail"],
                "argumentos_mal": argumentos_mal,
                "llamadas": sum(paso["kind"] == "tool" for paso in resultado["steps"]),
                "argumentos": [
                    {"name": paso["name"], "arguments": paso["arguments"]}
                    for paso in resultado["steps"]
                    if paso["kind"] == "tool"
                ],
                "metricas": vuelta["metrics"] if vuelta else None,
                "texto": vuelta["content"] if vuelta else "",
            }
            filas.append(fila)
            segundos = vuelta["metrics"]["total_s"] if vuelta else float("nan")
            print(
                f"  {'OK   ' if acierto else 'FALLO'} {categoria:12} {segundos:5.1f} s  "
                f"{sorted(pedidas) or '-'}{'' if resultado['status'] != 'failed' else '  ' + str(resultado['detail'])}"
            )

        por_categoria = Counter(fila["categoria"] for fila in filas)
        aciertos = Counter(fila["categoria"] for fila in filas if fila["acierto"])
        tiempos = [fila["metricas"]["total_s"] for fila in filas if fila["metricas"]]
        salidas = [fila["metricas"]["output_tokens"] or 0 for fila in filas if fila["metricas"]]
        print(f"  -- think {etiqueta}")
        for categoria in por_categoria:
            print(f"     {categoria:12} {aciertos[categoria]}/{por_categoria[categoria]}")
        print(f"     {'TOTAL':12} {sum(aciertos.values())}/{len(filas)}")
        print(
            f"     argumentos que no encajan: {sum(fila['argumentos_mal'] for fila in filas)} "
            f"de {sum(fila['llamadas'] for fila in filas)} llamadas"
        )
        print(
            f"     genéricas resueltas con analyze_headline: "
            f"{sum('analyze_headline' in fila['pedidas'] for fila in filas if fila['categoria'] == 'GENERICA')}"
        )
        print(
            f"     vuelta del modelo: mediana {_mediana(tiempos):.1f} s · mín {min(tiempos, default=0):.1f} · "
            f"máx {max(tiempos, default=0):.1f} · tokens de salida, mediana {_mediana(salidas):.0f}"
        )
        registro["seleccion"][etiqueta] = filas
        _guardar(registro)


# ----- 3 · Bucles completos -----


def _resumen_bucle(nombre: str, resultado: dict) -> dict:
    vueltas = [paso for paso in resultado["steps"] if paso["kind"] == "model"]
    llamadas = [paso for paso in resultado["steps"] if paso["kind"] == "tool"]
    return {
        "nombre": nombre,
        "estado": resultado["status"],
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
        "herramientas": [
            {
                "name": llamada["name"],
                "arguments": llamada["arguments"],
                "status": llamada["status"],
                "error": llamada["error"],
                "duration_s": llamada["duration_s"],
                "caracteres": len(json.dumps(llamada["data"], ensure_ascii=False, default=str)),
            }
            for llamada in llamadas
        ],
        "respuesta": resultado["answer"],
        "total_s": resultado["total_s"],
        "traza": resultado["steps"],
    }


def _imprimir_bucle(resumen: dict, etiqueta: str) -> None:
    print(f"\n  -- {resumen['nombre']} ({etiqueta}): {resumen['estado']}, {len(resumen['vueltas'])} vueltas, {resumen['total_s']:.1f} s")
    for indice, vuelta in enumerate(resumen["vueltas"], 1):
        print(
            f"     vuelta {indice}: prompt_tokens {vuelta['prompt_tokens']!s:>5} · salida {vuelta['output_tokens']!s:>4} · "
            f"{vuelta['total_s']:.1f} s · pide {vuelta['pide'] or '-'}"
        )
    for llamada in resumen["herramientas"]:
        print(
            f"     {llamada['name']}({json.dumps(llamada['arguments'], ensure_ascii=False)[:80]}) → "
            f"{llamada['status']}, {llamada['caracteres']} caracteres, {llamada['duration_s']:.1f} s"
            + (f" · {llamada['error']}" if llamada["error"] else "")
        )
    print("     respuesta:", resumen["respuesta"].replace("\n", " ") or "(vacía)")


async def bucles(registro: dict) -> None:
    registro["bucles"] = {"enteros": [], "recortados": [], "con_think": []}

    print("\n== bucles completos, think false, resultados enteros")
    for nombre, consulta, historial in BUCLES:
        resumen = _resumen_bucle(nombre, await responder(consulta, historial, _config(False)))
        registro["bucles"]["enteros"].append(resumen)
        _imprimir_bucle(resumen, "entero")
        _guardar(registro)

    grandes = [
        (nombre, consulta, historial)
        for (nombre, consulta, historial), resumen in zip(BUCLES, registro["bucles"]["enteros"], strict=True)
        if any(llamada["caracteres"] > RECORTE for llamada in resumen["herramientas"])
    ]
    print(f"\n== los que devolvieron más de {RECORTE} caracteres, recortados a esa cifra: {[nombre for nombre, _, _ in grandes]}")
    for nombre, consulta, historial in grandes:
        resultado = await responder(consulta, historial, _config(False, max_result_chars=RECORTE))
        resumen = _resumen_bucle(nombre, resultado)
        registro["bucles"]["recortados"].append(resumen)
        _imprimir_bucle(resumen, f"recortado a {RECORTE}")
        _guardar(registro)

    print("\n== con think true")
    for nombre, consulta, historial in BUCLES:
        if nombre not in BUCLES_CON_THINK:
            continue
        resumen = _resumen_bucle(nombre, await responder(consulta, historial, _config(True)))
        registro["bucles"]["con_think"].append(resumen)
        _imprimir_bucle(resumen, "think true")
        _guardar(registro)

    tiempos = [resumen["total_s"] for resumen in registro["bucles"]["enteros"]]
    print(f"\n  bucles enteros de punta a punta: mediana {_mediana(tiempos):.1f} s · mín {min(tiempos):.1f} · máx {max(tiempos):.1f}")


async def definitiva(registro: dict) -> None:
    """La configuración que se queda: razonando, entero y sin sangría."""
    await contexto(registro)
    await seleccion(registro, {"true": True})

    registro["bucles"] = {"con_think": []}
    print("\n== bucles completos, think true, resultados enteros")
    for nombre, consulta, historial in BUCLES:
        resumen = _resumen_bucle(nombre, await responder(consulta, historial, _config(True)))
        registro["bucles"]["con_think"].append(resumen)
        _imprimir_bucle(resumen, "think true")
        _guardar(registro)

    tiempos = [resumen["total_s"] for resumen in registro["bucles"]["con_think"]]
    maximo = max(
        vuelta["prompt_tokens"] or 0
        for resumen in registro["bucles"]["con_think"]
        for vuelta in resumen["vueltas"]
    )
    print(
        f"\n  bucles de punta a punta: mediana {_mediana(tiempos):.1f} s · "
        f"mín {min(tiempos):.1f} · máx {max(tiempos):.1f} · "
        f"prompt_tokens máximo {maximo} de {NUM_CTX}"
    )


REPETICIONES_SIN_CUERPO = 3


async def cuerpo(registro: dict) -> None:
    """#197: sin cuerpo, ¿qué `content` manda el modelo, y queda la incoherencia fuera?"""
    consultas = [
        consulta for categoria, consulta, _ in PRUEBAS if categoria == "GENERICA"
    ] + [consulta for nombre, consulta, _ in BUCLES if nombre == "analisis-completo"]
    print(
        f"\n== sin cuerpo: {len(consultas)} consultas × {REPETICIONES_SIN_CUERPO}, "
        "razonando, max_rounds=1"
    )
    filas = []
    for consulta in consultas:
        for repeticion in range(1, REPETICIONES_SIN_CUERPO + 1):
            resultado = await responder(consulta, [], _config(True, max_rounds=1))
            llamadas = [paso for paso in resultado["steps"] if paso["kind"] == "tool"]
            analisis = [paso for paso in llamadas if paso["name"] == "analyze_headline"]
            if not analisis:
                fila = {
                    "consulta": consulta,
                    "repeticion": repeticion,
                    "herramientas": [paso["name"] for paso in llamadas],
                }
                print(f"  {repeticion} · sin analyze_headline: {fila['herramientas'] or '-'}")
                filas.append(fila)
                continue
            for paso in analisis:
                datos = paso["data"] or {}
                senales = {senal["name"]: senal for senal in datos.get("signals", [])}
                fila = {
                    "consulta": consulta,
                    "repeticion": repeticion,
                    "content": paso["arguments"].get("content", "(sin el parámetro)"),
                    "incoherencia": senales.get("detect_clickbait_incoherence", {}).get("status"),
                    "veredicto": datos.get("verdict"),
                    "error": paso["error"],
                }
                print(
                    f"  {repeticion} · content={fila['content']!r:24} → incoherencia "
                    f"{fila['incoherencia']} · veredicto {fila['veredicto']}"
                    + (f" · {fila['error']}" if fila["error"] else "")
                )
                filas.append(fila)
        _guardar(registro | {"cuerpo": filas})

    con_analisis = [fila for fila in filas if "content" in fila]
    print(f"\n  llamadas a analyze_headline: {len(con_analisis)} de {len(filas)} intentos")
    print(f"  content enviado: {dict(Counter(repr(fila['content']) for fila in con_analisis))}")
    print(f"  incoherencia: {dict(Counter(fila['incoherencia'] for fila in con_analisis))}")
    print(f"  veredicto: {dict(Counter(fila['veredicto'] for fila in con_analisis))}")
    registro["cuerpo"] = filas
    _guardar(registro)


PARTES = {
    "contexto": contexto,
    "seleccion": seleccion,
    "bucles": bucles,
    "definitiva": definitiva,
    "cuerpo": cuerpo,
}
PRIMERA_SESION = ["contexto", "seleccion", "bucles"]


async def main(partes: list[str]) -> None:
    async with httpx.AsyncClient() as cliente:
        version = (await cliente.get(f"{URL}/api/version")).json()["version"]
    registro: dict = {
        "condiciones": {
            "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
            "commit": subprocess.run(
                ["git", "-C", str(RAIZ), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=False,
            ).stdout.strip(),
            "ollama": version,
            "servidor": URL,
            "modelo": MODELO,
            "num_ctx": NUM_CTX,
            "prompt": PROMPT,
            "partes": partes,
        }
    }
    print("== condiciones")
    for clave, valor in registro["condiciones"].items():
        print(f"  {clave}: {valor}")

    app = SERVIDOR.streamable_http_app()
    # El gestor de sesiones de FastMCP arranca en el lifespan, que
    # ASGITransport no ejecuta: se entra a mano (como en los tests).
    async with app.router.lifespan_context(app):
        mcp_session._http_client = lambda corte: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE, timeout=corte
        )
        for parte in partes:
            await PARTES[parte](registro)

    _guardar(registro)
    print(f"\nTodo lo medido, con las respuestas enteras: {SALIDA}")


if __name__ == "__main__":
    elegidas = sys.argv[1:] or PRIMERA_SESION
    desconocidas = [parte for parte in elegidas if parte not in PARTES]
    if desconocidas:
        sys.exit(f"Partes desconocidas: {desconocidas}. Hay: {list(PARTES)}")
    asyncio.run(main(elegidas))
