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

Y una sexta, de #78 (2026-10-06), para comparar docstrings sin depender de la
suerte de una sesión:

6. `variantes`: las 26 consultas con tres variantes de los docstrings del lineal
   y del léxico, intercaladas en la misma sesión y repetidas
   (`AGENTE_A40_REPETICIONES`, dos por defecto), en las dos condiciones que
   razonan. Sólo cambia la descripción de esas dos herramientas en el mismo
   objeto `mcp`.

Y una séptima, de #234 (2026-10-09), para cerrar `v0.8`:

7. `cierre`: las 26 consultas y ocho en español, contadas aparte, con el
   catálogo de `v0.7.0` (`antes`: 12 herramientas y sus textos) y el de ahora
   (`nuevo`: 14, con los docstrings y el `05-llano` que dicen inglés y español),
   intercaladas y repetidas (`AGENTE_A40_REPETICIONES`, cuatro por defecto), en
   las condiciones de producción: `05-llano`, `num_ctx` 16384, el perfil
   preciso, el tope de salida y razonando. Antes de gastar la sesión comprueba
   que `antes` es, letra a letra, lo que publicaba el tag `v0.7.0`
   (`--comprobar-cierre` lo hace sin sesión). En español cuenta además si el
   titular llega a la herramienta tal cual o cambiado. Y al final, cuatro
   conversaciones completas en español con `nuevo`, para leerlas.

   La primera sesión (2026-10-09, `spikes/agente_a40/cierre-234.json`)
   midió los textos de `216c525` y no cumplió la regla de las 26 por una
   consulta; la segunda (`cierre-234b.json`) mide la variante `v2`, con las
   dos frases de la frontera de #183 recuperadas y el «Raises» de la
   dedicada y el tono, que #236 había dejado para F.

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

El resumen de `variantes` —totales, la regla de #78 y los aciertos de cada
consulta— se rehace sin sesión desde lo guardado:

    .venv/bin/python spikes/agente_a40.py --analisis spikes/agente_a40/variantes-78.json

y el de `cierre`, igual:

    .venv/bin/python spikes/agente_a40.py --analisis-cierre spikes/agente_a40/cierre-234.json
"""

import ast
import asyncio
import inspect
import json
import logging
import os
import re
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
from backend.config.settings import Settings  # noqa: E402
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
        # El aviso del historial llegó en #192; sin él, como se midió #188.
        aviso_historial=None,
        # Y pedir la respuesta cuando sale vacía, en #208: también apagado.
        pedir_respuesta_si_vacia=None,
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


async def _elegir(
    categoria: str, consulta: str, aceptables: set[str], config: Configuracion
) -> dict:
    """Una consulta cortada donde diga `config`: qué pide el modelo y si acierta.

    Sin herramientas aceptables, acierta si no pide ninguna."""
    resultado = await responder(consulta, [], config)
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
    segundos = vuelta["metrics"]["total_s"] if vuelta else float("nan")
    print(
        f"  {'OK   ' if acierto else 'FALLO'} {categoria:12} {segundos:5.1f} s  "
        f"{sorted(pedidas) or '-'}{'' if resultado['status'] != 'failed' else '  ' + str(resultado['detail'])}"
    )
    return fila


async def seleccion(
    registro: dict, condiciones: dict | None = None, raiz: dict | None = None
) -> None:
    """`raiz`, si se da, es el registro entero que se guarda (lo usa `variantes`,
    que pasa aquí sólo la pasada en curso)."""
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
            filas.append(
                await _elegir(categoria, consulta, aceptables, _config(think, max_rounds=1))
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
        _guardar(registro if raiz is None else raiz)


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


# ----- 6 · Variantes de docstring, intercaladas en la misma sesión (#78) -----

# Cada variante es una lista de (herramienta, frase de `v1`, frase de la
# variante) sobre la descripción SIN SANGRÍA, que es la que manda el agente
# (`inspect.cleandoc`, `agente.py`). `v1` es la de producción en el commit
# medido: el guion comprueba que cada frase está una vez, así que si el
# docstring cambia, la parte se niega a medir en vez de comparar otra cosa.
_LINEAL = "detect_clickbait_linear"
_LEXICO = "detect_clickbait_lexical"
_V1_LINEAL = (
    "Es el modelo entrenado en este proyecto: una regresión logística sobre\n"
    "las palabras del titular y su estructura (número inicial,\n"
    "interrogación…), en la que cada palabra tiene un peso visible. El\n"
    "veredicto se explica con las que más pesaron. Para la opinión de un\n"
    "modelo sin pesos visibles, `detect_clickbait` (caja negra). Pensada\n"
    "para inglés."
)
_V1_DEVUELVE = "—las palabras que más empujaron el veredicto (peso × tf-idf), que"
_V1_LEXICO = "(que pondera las palabras del titular)"
VARIANTES_DOCSTRING = {
    # Los textos de #124 y #159: falsos con el lineal de #78, sólo la vara de medir.
    "antes": [
        (
            _LINEAL,
            _V1_LINEAL,
            "Es el modelo entrenado en este proyecto: una regresión logística sobre\n"
            "pistas léxicas (hipérbole, referencias vagas, listas numeradas…), en la\n"
            "que cada pista tiene un peso visible. El veredicto se explica con las\n"
            "pistas que más pesaron. Para la opinión de un modelo que no parte de\n"
            "esas pistas, `detect_clickbait` (caja negra). Pensada para inglés.",
        ),
        (
            _LINEAL,
            _V1_DEVUELVE,
            "—las pistas que más empujaron el veredicto (peso × frecuencia), que",
        ),
        (_LEXICO, _V1_LEXICO, "(que pondera estas mismas pistas)"),
    ],
    "v1": [],
    # El texto de antes, cambiando sólo lo que es falso con el lineal de #78.
    "v2": [
        (
            _LINEAL,
            _V1_LINEAL,
            "Es el modelo entrenado en este proyecto: una regresión logística sobre\n"
            "las pistas del titular —sus palabras y su estructura—, en la que cada\n"
            "pista tiene un peso visible. El veredicto se explica con las pistas que\n"
            "más pesaron. Para la opinión de un modelo que no parte de esas pistas,\n"
            "`detect_clickbait` (caja negra). Pensada para inglés.",
        ),
        (
            _LINEAL,
            _V1_DEVUELVE,
            "—las pistas que más empujaron el veredicto (peso × tf-idf), que",
        ),
        (
            _LEXICO,
            _V1_LEXICO,
            "(que pondera estas pistas y el resto de palabras del titular)",
        ),
    ],
}
REPETICIONES_VARIANTES = int(os.environ.get("AGENTE_A40_REPETICIONES", "2"))
CONDICIONES_QUE_RAZONAN = {"sin campo": None, "true": True}


def _descripciones_de(variante: str, originales: dict[str, str]) -> dict[str, str]:
    """Las descripciones de las dos herramientas en una variante."""
    descripciones = dict(originales)
    for herramienta, frase_v1, frase in VARIANTES_DOCSTRING[variante]:
        veces = descripciones[herramienta].count(frase_v1)
        if veces != 1:
            raise SystemExit(
                f"ABORTADO: la frase de v1 de {herramienta} está {veces} veces en la "
                "descripción publicada; el docstring ya no es el que esta parte compara."
            )
        descripciones[herramienta] = descripciones[herramienta].replace(frase_v1, frase)
    return descripciones


async def variantes(registro: dict) -> None:
    """Las 26 consultas con cada variante, intercaladas, razonando (#78).

    Una sola sesión por variante no separa el docstring de la suerte: con el
    muestreo del Modelfile, el mismo examen dio 23, 25 y 26 en sesiones
    distintas. Aquí, en cada repetición, las tres variantes una tras otra, con
    las dos condiciones que razonan (`false` no lo usa el agente). Sólo cambia
    la descripción de dos herramientas en el mismo objeto `mcp`; al terminar,
    vuelve la de producción.
    """
    gestor = SERVIDOR._tool_manager
    originales = {
        nombre: inspect.cleandoc(gestor.get_tool(nombre).description)
        for nombre in (_LINEAL, _LEXICO)
    }
    # Que se puedan construir todas ANTES de gastar la sesión.
    textos = {variante: _descripciones_de(variante, originales) for variante in VARIANTES_DOCSTRING}
    registro["variantes"] = {"textos": textos, "pasadas": []}
    try:
        for repeticion in range(1, REPETICIONES_VARIANTES + 1):
            for variante, descripciones in textos.items():
                for nombre, descripcion in descripciones.items():
                    gestor.get_tool(nombre).description = descripcion
                print(f"\n######## repetición {repeticion} · variante {variante}")
                pasada = {"repeticion": repeticion, "variante": variante}
                registro["variantes"]["pasadas"].append(pasada)
                await seleccion(pasada, CONDICIONES_QUE_RAZONAN, raiz=registro)
    finally:
        for nombre, descripcion in originales.items():
            gestor.get_tool(nombre).description = descripcion

    resumen_variantes(registro["variantes"])


# La regla, publicada en #78 antes de la sesión (comentario 6018323652): una
# variante se queda si (a) su total no baja más de MARGEN_VARIANTES del de
# `antes`, y (b) ninguna consulta que `antes` acierta en todas sus pasadas la
# falla en todas la variante.
MARGEN_VARIANTES = 2


def resumen_variantes(medido: dict) -> None:
    """Los totales, la regla de #78 y los aciertos de cada consulta.

    Sólo lee lo guardado en `medido` (el `variantes` del JSON), así que se
    repite sin sesión de GPU con `--analisis <json>`.
    """
    totales: dict[str, list[int]] = {}
    posibles: dict[str, int] = {}
    aciertos: dict[str, dict[str, list[bool]]] = {}
    for pasada in medido["pasadas"]:
        variante = pasada["variante"]
        filas = [fila for filas in pasada["seleccion"].values() for fila in filas]
        totales.setdefault(variante, []).append(sum(fila["acierto"] for fila in filas))
        posibles[variante] = posibles.get(variante, 0) + len(filas)
        por_consulta = aciertos.setdefault(variante, {})
        for fila in filas:
            por_consulta.setdefault(fila["consulta"], []).append(bool(fila["acierto"]))

    print("\n== variantes: aciertos razonando (sin campo + true), por repetición")
    for variante, suyos in totales.items():
        print(f"  {variante:6s} {' + '.join(map(str, suyos))} = {sum(suyos)}/{posibles[variante]}")

    referencia = aciertos["antes"]
    minimo = sum(totales["antes"]) - MARGEN_VARIANTES
    print(f"\n== la regla de #78: (a) total ≥ {minimo}; (b) nada que `antes` acierta siempre, fallado siempre")
    for variante in aciertos:
        if variante == "antes":
            continue
        suficiente = sum(totales[variante]) >= minimo
        rotas = [
            consulta
            for consulta, suyos in aciertos[variante].items()
            if all(referencia[consulta]) and not any(suyos)
        ]
        veredicto = "cumple" if suficiente and not rotas else "NO cumple"
        print(
            f"  {variante:6s} (a) {sum(totales[variante])}: {'sí' if suficiente else 'no'}"
            f" · (b) {rotas or 'ninguna'} → {veredicto}"
        )

    print("\n== aciertos de las consultas que alguna variante falla alguna vez")
    print("  " + " ".join(f"{variante:>5}" for variante in aciertos) + "  consulta")
    for consulta, intentos in referencia.items():
        cuentas = [sum(aciertos[variante][consulta]) for variante in aciertos]
        if min(cuentas) < len(intentos):
            print("  " + " ".join(f"{cuenta:>5}" for cuenta in cuentas) + f"  {consulta}")


# ----- 7 · El cierre de `v0.8`: el catálogo de `v0.7.0` contra el de ahora (#234) -----

# Cada frase de producción (`nuevo`) con la que había en `v0.7.0` (`antes`),
# herramienta a herramienta, sobre la descripción SIN SANGRÍA. Como en
# `variantes`, cada frase de `nuevo` tiene que estar una vez; y además
# `_preparar_cierre` comprueba que `antes` es lo que publicaba el tag.
CIERRE_ANTES = [
    (
        "detect_clickbait",
        "titulares anotados por personas, uno por idioma (el inglés, fuera de\n"
        "este proyecto); por",
        "titulares anotados por personas, fuera de este proyecto; por",
    ),
    (
        "detect_clickbait",
        "`detect_clickbait_lexical`. Analiza titulares en inglés y en español.",
        "`detect_clickbait_lexical`. Pensada para inglés.",
    ),
    (
        "detect_clickbait",
        "headline (str): titular a evaluar (en inglés o en español).",
        "headline (str): titular a evaluar (en inglés).",
    ),
    (
        "analyze_sentiment",
        "Clasifica en tres clases: positive, neutral o negative, con un modelo\n"
        "para el inglés y otro para el español. Útil para medir el tono.",
        "Clasifica en tres clases: positive, neutral o negative (modelo en\n"
        "inglés, afinado para texto corto). Útil para medir el tono.",
    ),
    (
        "analyze_sentiment",
        "text (str): texto a analizar (en inglés o en español).",
        "text (str): texto a analizar (en inglés).",
    ),
    (
        "detect_clickbait_incoherence",
        "Sólo en inglés, titular y cuerpo: en español la similitud apenas\n"
        "distingue el clickbait, y no se aplica.",
        "Pensada para texto en inglés.",
    ),
    (
        "detect_clickbait_lexical",
        "`detect_clickbait_incoherence`. Sólo inglés: sus listas de pistas son\ninglesas.",
        "`detect_clickbait_incoherence`. Pensada para titulares en inglés.",
    ),
    (
        "detect_clickbait_linear",
        "(caja negra). Bilingüe:\nlos mismos pesos para el inglés y el español.",
        "(caja negra). Pensada\npara inglés.",
    ),
    (
        "detect_clickbait_linear",
        "headline (str): titular a evaluar (en inglés o en español).",
        "headline (str): titular a evaluar (en inglés).",
    ),
    (
        "describe_models",
        "Devuelve, por cada señal y cada idioma que analiza, su nombre, tarea,\n"
        "tipo (interpretable / híbrido / opaco), dimensión que mide y\n"
        "limitaciones conocidas. Sin argumentos. Útil para la transparencia de\n"
        "sistema y para decidir qué señal usar según su naturaleza (white-box vs\n"
        "caja negra) y sus límites.",
        "Devuelve, por cada señal, su nombre, tarea, tipo (interpretable /\n"
        "híbrido / opaco), dimensión que mide y limitaciones conocidas. Sin\n"
        "argumentos. Útil para la transparencia de sistema y para decidir qué\n"
        "señal usar según su naturaleza (white-box vs caja negra) y sus límites.",
    ),
    (
        "describe_models",
        "La lista de fichas de modelo (signal, language, model_id, revision,\n"
        "    name, task, type, dimension, limitations, backend).",
        "La lista de fichas de modelo (signal, name, task, type, dimension,\n"
        "    limitations, backend).",
    ),
    (
        "analyze_headline",
        "headline: El titular a analizar, en inglés o en español; en\n"
        "        español, el léxico y la incoherencia no se aplican.",
        "headline: El titular a analizar, en inglés.",
    ),
]
CIERRE_ANTES += [
    (
        herramienta,
        "Si el modelo falla: no se puede cargar o, por la vía remota, no\n    responde (timeout, caída del proveedor o falta de crédito).",
        "Si la llamada al modelo falla (timeout o caída del proveedor).",
    )
    for herramienta in ("detect_clickbait", "analyze_sentiment")
]
# Las dos de #235: en `v0.7.0` no estaban.
NO_ESTABAN_EN_V070 = ("get_gnews_news", "get_newsdata_news")
TAG_ANTES = "v0.7.0"
PROMPT_CIERRE = "05-llano"
PROMPT_NUEVO = (
    "Las herramientas analizan titulares en inglés y en español; en español, el\n"
    "detector de pistas y el comparador de titular y texto no se aplican. Si el\n"
    "titular está en otro idioma, avísalo antes de analizarlo."
)
PROMPT_ANTES = (
    "Las herramientas están entrenadas con titulares de noticias en inglés. Si el\n"
    "titular está en otro idioma, avísalo antes de analizarlo."
)

NOTICIAS_ES = {"get_gnews_news", "get_newsdata_news"}
CONSULTAS_ES = [
    (
        "ES_GENERICA",
        "¿Es clickbait este titular? 'No vas a creer lo que hizo este perro al ver a su dueño'",
        GENERICA_ACEPTABLE,
    ),
    (
        "ES_GENERICA",
        "Analiza si esto es clickbait: 'El Banco Central Europeo sube los tipos de interés un cuarto de punto'",
        GENERICA_ACEPTABLE,
    ),
    (
        "ES_GENERICA",
        "Analiza a fondo el titular 'Lo que descubrieron en este pueblo te dejará sin palabras' con todas las señales del sistema",
        {"analyze_headline"},
    ),
    (
        "ES_LINEAL",
        "Dame la probabilidad de clickbait de 'Los 10 trucos que los médicos no quieren que conozcas'",
        {"detect_clickbait_linear"},
    ),
    (
        "ES_CAJA_NEGRA",
        "Quiero la opinión del modelo de caja negra sobre 'Así reaccionó la actriz al ver su nueva casa'",
        {"detect_clickbait"},
    ),
    (
        "ES_TONO",
        "¿Qué tono tiene el titular 'Una celebración maravillosa llena las calles de la ciudad'?",
        {"analyze_sentiment"},
    ),
    ("ES_NOTICIAS", "Busca noticias en español sobre inteligencia artificial", NOTICIAS_ES),
    ("ES_NOTICIAS", "¿Qué publican los medios en español sobre las elecciones?", NOTICIAS_ES),
]
CONVERSACIONES_ES = [
    ("es-generica", "¿Es clickbait 'No vas a creer lo que hizo este perro al ver a su dueño'?"),
    (
        "es-lexico",
        "¿Qué pistas léxicas tiene el titular 'Increíble: lo que pasó después te sorprenderá'?",
    ),
    (
        "es-incoherencia",
        "¿El titular 'Descubren la cura milagrosa que acaba con el envejecimiento' encaja "
        "con el texto 'Un pequeño ensayo "
        "halló efectos modestos en ratones tras ocho semanas'?",
    ),
    (
        "es-noticia",
        "Busca una noticia en español sobre el clima y dime si su titular es clickbait.",
    ),
]
REPETICIONES_CIERRE = int(os.environ.get("AGENTE_A40_REPETICIONES", "4"))


def _config_produccion(prompt: str, **cambios) -> Configuracion:
    """El agente como lo monta la API (`api/chat.py`), con los valores por
    defecto de `Settings`, que son los de producción: el compose sólo fija el
    backend y la URL. Cambian el servidor —el túnel propio— y los cortes de
    MCP, porque aquí las señales se ejecutan en el proceso y cargan en frío."""
    defecto = {nombre: campo.default for nombre, campo in Settings.model_fields.items()}
    backend = OllamaClient(
        URL,
        MODELO,
        num_ctx=defecto["llm_num_ctx"],
        keep_alive=defecto["llm_keep_alive"],
        timeout=defecto["llm_timeout"],
        temperature=defecto["llm_temperature"],
        presence_penalty=defecto["llm_presence_penalty"],
        num_predict=defecto["llm_num_predict"],
    )
    return Configuracion(
        backend=backend,
        servers=[_SERVIDOR_URL],
        prompt=prompt,
        discovery_timeout=10.0,
        execute_timeout=120.0,
        **cambios,
    )


def _en_el_tag(ruta_en_el_repo: str) -> str:
    return subprocess.run(
        ["git", "-C", str(RAIZ), "show", f"{TAG_ANTES}:{ruta_en_el_repo}"],
        capture_output=True, text=True, check=True,
    ).stdout


def _docstrings_en_el_tag(modulo: str) -> dict[str, str]:
    """Los docstrings de las funciones de un módulo, como estaban en el tag."""
    arbol = ast.parse(_en_el_tag(modulo.replace(".", "/") + ".py"))
    return {
        nodo.name: ast.get_docstring(nodo) or ""
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def _preparar_cierre() -> dict:
    """Los textos de las dos versiones, comprobados ANTES de gastar la sesión.

    `antes` se reconstruye sobre el catálogo de ahora, deshaciendo las frases
    de `CIERRE_ANTES` y escondiendo las herramientas nuevas; y se compara,
    herramienta a herramienta, con los docstrings del tag `v0.7.0`, y el
    prompt con su fichero allí. Si algo no casa, no se mide nada."""
    gestor = SERVIDOR._tool_manager
    nuevas = {
        nombre: inspect.cleandoc(herramienta.description or "")
        for nombre, herramienta in gestor._tools.items()
    }
    faltan = [nombre for nombre in NO_ESTABAN_EN_V070 if nombre not in nuevas]
    if faltan:
        raise SystemExit(f"ABORTADO: no están en el catálogo {faltan}.")
    viejas = {nombre: texto for nombre, texto in nuevas.items() if nombre not in NO_ESTABAN_EN_V070}
    for herramienta, frase_nueva, frase_vieja in CIERRE_ANTES:
        veces = viejas[herramienta].count(frase_nueva)
        if veces != 1:
            raise SystemExit(
                f"ABORTADO: la frase de producción de {herramienta} está {veces} veces; "
                "el docstring ya no es el que esta parte compara."
            )
        viejas[herramienta] = viejas[herramienta].replace(frase_nueva, frase_vieja)

    distintas = []
    for nombre, texto in viejas.items():
        modulo = gestor._tools[nombre].fn.__module__
        if _docstrings_en_el_tag(modulo).get(nombre) != texto:
            distintas.append(f"{nombre} ({modulo})")
    if distintas:
        raise SystemExit(f"ABORTADO: `antes` no es lo de {TAG_ANTES} en {distintas}.")

    prompt_nuevo = prompts.cargar(PROMPT_CIERRE)
    if prompt_nuevo.count(PROMPT_NUEVO) != 1:
        raise SystemExit(f"ABORTADO: el párrafo nuevo no está una vez en `{PROMPT_CIERRE}`.")
    prompt_viejo = prompt_nuevo.replace(PROMPT_NUEVO, PROMPT_ANTES)
    if prompt_viejo != _en_el_tag(f"backend/agent/prompts/{PROMPT_CIERRE}.md"):
        raise SystemExit(f"ABORTADO: el `{PROMPT_CIERRE}` de antes no es el de {TAG_ANTES}.")

    return {
        "antes": {
            "descripciones": viejas,
            "prompt": prompt_viejo,
            "escondidas": list(NO_ESTABAN_EN_V070),
        },
        "nuevo": {"descripciones": nuevas, "prompt": prompt_nuevo, "escondidas": []},
    }


async def cierre(registro: dict) -> None:
    """Las 26 y las de español con `antes` y `nuevo`, intercaladas (#234).

    La regla, publicada en #234 antes de la sesión, es la de #78 para las 26
    (`resumen_cierre`). En cada repetición van las dos versiones, en orden
    alterno, y sólo cambian las descripciones, las herramientas escondidas y
    el prompt; al terminar vuelve todo a producción."""
    versiones = _preparar_cierre()
    gestor = SERVIDOR._tool_manager
    originales = {nombre: herramienta.description for nombre, herramienta in gestor._tools.items()}
    escondibles = {nombre: gestor._tools[nombre] for nombre in NO_ESTABAN_EN_V070}
    pruebas = (
        [
            (categoria, consulta, GENERICA_ACEPTABLE if categoria == "GENERICA" else aceptables)
            for categoria, consulta, aceptables in PRUEBAS
        ]
        + [("CONTRASTE", consulta, aceptables) for _, consulta, aceptables in CONTRASTE]
        + CONSULTAS_ES
    )
    # La cabecera del registro lleva las constantes de las partes viejas
    # (`04-preciso`, 8192): las de ésta son las de producción, y van aquí.
    defecto = {nombre: campo.default for nombre, campo in Settings.model_fields.items()}
    condiciones = {
        "prompt": PROMPT_CIERRE,
        "think": True,
        "repeticiones": REPETICIONES_CIERRE,
        **{
            nombre: defecto[nombre]
            for nombre in (
                "llm_num_ctx",
                "llm_temperature",
                "llm_presence_penalty",
                "llm_num_predict",
                "llm_keep_alive",
                "llm_timeout",
            )
        },
    }
    print(f"\n== cierre, condiciones: {condiciones}")
    registro["cierre"] = {
        "condiciones": condiciones,
        "versiones": versiones,
        "pasadas": [],
        "conversaciones": [],
    }
    try:
        for repeticion in range(1, REPETICIONES_CIERRE + 1):
            orden = list(versiones) if repeticion % 2 else list(reversed(versiones))
            for version in orden:
                textos = versiones[version]
                for nombre, herramienta in escondibles.items():
                    if nombre in textos["escondidas"]:
                        gestor._tools.pop(nombre, None)
                    else:
                        gestor._tools[nombre] = herramienta
                for nombre, descripcion in textos["descripciones"].items():
                    gestor._tools[nombre].description = descripcion
                print(f"\n######## repetición {repeticion} · {version}: {len(gestor._tools)} herramientas")
                filas = []
                for categoria, consulta, aceptables in pruebas:
                    config = _config_produccion(textos["prompt"], max_rounds=1)
                    filas.append(await _elegir(categoria, consulta, aceptables, config))
                registro["cierre"]["pasadas"].append(
                    {"repeticion": repeticion, "version": version, "filas": filas}
                )
                _guardar(registro)
    finally:
        gestor._tools.update(escondibles)
        for nombre, descripcion in originales.items():
            gestor._tools[nombre].description = descripcion

    print("\n== conversaciones completas en español, con `nuevo`")
    for nombre, consulta in CONVERSACIONES_ES:
        resultado = await responder(consulta, [], _config_produccion(versiones["nuevo"]["prompt"]))
        resumen = _resumen_bucle(nombre, resultado)
        registro["cierre"]["conversaciones"].append(resumen)
        _imprimir_bucle(resumen, "nuevo")
        _guardar(registro)

    resumen_cierre(registro["cierre"])


def _titulares_cambiados(fila: dict) -> list[tuple[str, str]]:
    """Las llamadas cuyo titular no es el de la consulta, tal cual."""
    entre_comillas = re.search(r"'([^']+)'", fila["consulta"])
    if entre_comillas is None:
        return []

    def normalizar(texto: str) -> str:
        return texto.strip().strip("'\"«»“”").strip().casefold()

    original = normalizar(entre_comillas.group(1))
    cambiados = []
    for llamada in fila["argumentos"]:
        argumentos = llamada["arguments"] or {}
        titular = argumentos.get("headline", argumentos.get("text"))
        if isinstance(titular, str) and normalizar(titular) != original:
            cambiados.append((llamada["name"], titular))
    return cambiados


def resumen_cierre(medido: dict) -> None:
    """Las dos reglas de #234 y los aciertos de cada consulta.

    Sólo lee lo guardado, así que se repite sin sesión con `--analisis-cierre`."""
    aciertos: dict[str, dict[str, list[bool]]] = {}
    categorias: dict[str, str] = {}
    cambiados: dict[str, list] = {}
    for pasada in medido["pasadas"]:
        version = pasada["version"]
        for fila in pasada["filas"]:
            aciertos.setdefault(version, {}).setdefault(fila["consulta"], []).append(
                bool(fila["acierto"])
            )
            categorias[fila["consulta"]] = fila["categoria"]
            if fila["categoria"].startswith("ES_"):
                for nombre, titular in _titulares_cambiados(fila):
                    cambiados.setdefault(version, []).append((fila["consulta"], nombre, titular))

    def en_espanol(consulta: str) -> bool:
        return categorias[consulta].startswith("ES_")

    def total(version: str, cuales) -> tuple[int, int]:
        intentos = [
            acierto
            for consulta, suyos in aciertos[version].items()
            if cuales(consulta)
            for acierto in suyos
        ]
        return sum(intentos), len(intentos)

    def las_26(consulta: str) -> bool:
        return not en_espanol(consulta)

    def comparables_es(consulta: str) -> bool:
        return en_espanol(consulta) and categorias[consulta] != "ES_NOTICIAS"

    def noticias_es(consulta: str) -> bool:
        return categorias[consulta] == "ES_NOTICIAS"

    print("\n== cierre: aciertos, por versión")
    for version in aciertos:
        print(
            f"  {version:6s} las 26: {'/'.join(map(str, total(version, las_26)))} · "
            f"español sin noticias: {'/'.join(map(str, total(version, comparables_es)))} · "
            f"noticias en español: {'/'.join(map(str, total(version, noticias_es)))}"
        )
    if "antes" not in aciertos or "nuevo" not in aciertos:
        return

    minimo = total("antes", las_26)[0] - MARGEN_VARIANTES
    rotas = [
        consulta
        for consulta in aciertos["antes"]
        if las_26(consulta) and all(aciertos["antes"][consulta]) and not any(aciertos["nuevo"][consulta])
    ]
    primera = total("nuevo", las_26)[0] >= minimo and not rotas
    print(
        f"\n== regla 1, la de #78 (las 26): (a) nuevo {total('nuevo', las_26)[0]} ≥ {minimo}; "
        f"(b) {rotas or 'ninguna'} → {'cumple' if primera else 'NO cumple'}"
    )
    traducidos = cambiados.get("nuevo", [])
    segunda = total("nuevo", comparables_es)[0] >= total("antes", comparables_es)[0]
    print(
        f"== regla 2 (español sin noticias): nuevo {total('nuevo', comparables_es)[0]} ≥ antes "
        f"{total('antes', comparables_es)[0]}: {'sí' if segunda else 'no'} · titulares cambiados "
        f"con nuevo: {len(traducidos)} (con antes: {len(cambiados.get('antes', []))}), "
        "leídos uno a uno abajo"
    )
    for version, lista in cambiados.items():
        for consulta, nombre, titular in lista:
            print(f"  {version:6s} {nombre}: «{titular}» ← {consulta}")

    print("\n== aciertos de las consultas que alguna versión falla alguna vez")
    print("  antes nuevo  consulta")
    for consulta, suyos in aciertos["antes"].items():
        nuevos = aciertos["nuevo"].get(consulta, [])
        if min(sum(suyos), sum(nuevos)) < len(suyos):
            print(f"  {sum(suyos):>5} {sum(nuevos):>5}  [{categorias[consulta]}] {consulta}")


PARTES = {
    "contexto": contexto,
    "seleccion": seleccion,
    "bucles": bucles,
    "definitiva": definitiva,
    "cuerpo": cuerpo,
    "variantes": variantes,
    "cierre": cierre,
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
    if sys.argv[1:2] == ["--analisis-cierre"]:
        guardado = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        resumen_cierre(guardado["cierre"])
        sys.exit()
    if sys.argv[1:2] == ["--comprobar-cierre"]:
        # Sin sesión: que `antes` y `nuevo` se pueden construir y que `antes` es el tag.
        comprobadas = _preparar_cierre()
        for version, textos in comprobadas.items():
            print(
                f"{version}: {len(textos['descripciones'])} herramientas, "
                f"escondidas {textos['escondidas'] or '-'}, prompt de {len(textos['prompt'])} caracteres"
            )
        print(f"`antes` es, letra a letra, lo que publicaba {TAG_ANTES}.")
        sys.exit()
    if sys.argv[1:2] == ["--analisis"]:
        # Sin sesión: el resumen de la parte `variantes`, desde su JSON.
        guardado = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        resumen_variantes(guardado["variantes"])
        sys.exit()
    elegidas = sys.argv[1:] or PRIMERA_SESION
    desconocidas = [parte for parte in elegidas if parte not in PARTES]
    if desconocidas:
        sys.exit(f"Partes desconocidas: {desconocidas}. Hay: {list(PARTES)}")
    asyncio.run(main(elegidas))
