"""Spike #82 - Fase 2: ¿elige BIEN la herramienta entre varias parecidas?

La Fase 1 probó que el mecanismo funciona con una sola tool. Aquí está el dato
que decide el issue: con el catálogo real -donde hay cuatro herramientas de
clickbait con nombres casi idénticos- ¿acierta el modelo?

DISEÑO: no todas las consultas tienen una única respuesta correcta.
  - GENÉRICA  ("¿es clickbait?")        -> cualquier tool de clickbait vale.
  - ESPECÍFICA ("¿qué pistas léxicas?") -> solo vale una; aquí se ve la confusión.
  - OTRO_DOMINIO                        -> comprueba que no se queda en clickbait.
  - SIN_TOOL                            -> comprueba que no invoca por inercia.
Mezclar genéricas y específicas en una sola cifra daría un número sin sentido,
así que se reportan por separado.

Las descripciones de las tools son las REALES (docstrings de tool.py), porque lo
que se mide es si el modelo sabe distinguirlas con los textos que tendrá en
producción. En el sistema final las genera FastMCP y llegan por MCP tools/list.

Ejecutar: python spikes/tool_calling_fase2.py [modelo] [num_ctx]
"""

import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
OLLAMA_URL = f"http://{OLLAMA_HOST}/api/chat"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:2b"
NUM_CTX = int(sys.argv[2]) if len(sys.argv) > 2 else 2048


def _tool(nombre, descripcion, propiedades, obligatorios):
    return {
        "type": "function",
        "function": {
            "name": nombre,
            "description": descripcion,
            "parameters": {
                "type": "object",
                "properties": propiedades,
                "required": obligatorios,
            },
        },
    }


_HEADLINE = {"headline": {"type": "string", "description": "Titular a evaluar (en inglés)."}}

TOOLS = [
    _tool(
        "detect_clickbait",
        "Detecta si un titular de noticia es clickbait o informativo (factual) usando "
        "clasificación zero-shot. Devuelve la etiqueta ganadora y su confianza.",
        _HEADLINE, ["headline"],
    ),
    _tool(
        "detect_clickbait_lexical",
        "Detecta clickbait por pistas léxicas y estructurales del titular: hipérbole, "
        "referencias vagas (this/these), número inicial (listicle), interrogación, "
        "mayúsculas, elipsis. Devuelve QUÉ pistas dispararon y DÓNDE.",
        _HEADLINE, ["headline"],
    ),
    _tool(
        "detect_clickbait_linear",
        "Detecta clickbait con un modelo lineal entrenado (regresión logística sobre "
        "pistas léxicas). Devuelve la PROBABILIDAD de clickbait y los cues que más "
        "contribuyeron al veredicto con su peso.",
        _HEADLINE, ["headline"],
    ),
    _tool(
        "detect_clickbait_incoherence",
        "Detecta clickbait midiendo la INCOHERENCIA entre el titular y el cuerpo de la "
        "noticia mediante similitud semántica. Requiere ambos textos: una similitud baja "
        "indica que el titular no se corresponde con lo que cuenta la noticia.",
        {
            "headline": _HEADLINE["headline"],
            "content": {"type": "string", "description": "Cuerpo o teaser con el que contrastar."},
        },
        ["headline", "content"],
    ),
    _tool(
        "analyze_sentiment",
        "Analiza el sentimiento de un texto y lo clasifica como positive, neutral o "
        "negative, con su confianza.",
        {"text": {"type": "string", "description": "Texto a analizar (en inglés)."}},
        ["text"],
    ),
    _tool(
        "get_nyt_news",
        "Busca noticias del New York Times sobre un tema, de los últimos días.",
        {
            "topic": {"type": "string", "description": "Tema a buscar."},
            "days": {"type": "integer", "description": "Días hacia atrás (por defecto 7)."},
        },
        [],
    ),
    _tool(
        "get_guardian_news",
        "Busca noticias de The Guardian sobre un tema, de los últimos días.",
        {
            "topic": {"type": "string", "description": "Tema a buscar."},
            "days": {"type": "integer", "description": "Días hacia atrás (por defecto 7)."},
        },
        [],
    ),
    _tool(
        "describe_models",
        "Divulga los modelos que emplea el sistema: nombre, tarea, tipo (interpretable, "
        "híbrido u opaco) y limitaciones conocidas. No recibe argumentos.",
        {}, [],
    ),
]

CLICKBAIT_CUALQUIERA = {
    "detect_clickbait", "detect_clickbait_lexical", "detect_clickbait_linear",
}

# (categoría, consulta, herramientas aceptables)  -- conjunto vacío = no debe llamar
PRUEBAS = [
    ("GENERICA", "¿Es clickbait este titular? '10 Amazing Things You Won't Believe'", CLICKBAIT_CUALQUIERA),
    ("GENERICA", "Analiza si esto es clickbait: 'Scientists Discover New Species'", CLICKBAIT_CUALQUIERA),
    ("GENERICA", "'You Won't Believe What Happened Next' — ¿es un titular engañoso?", CLICKBAIT_CUALQUIERA),
    ("GENERICA", "Evalúa este titular: 'Top 5 Secrets Finally Revealed'", CLICKBAIT_CUALQUIERA),

    ("ESPECIFICA", "¿Qué pistas léxicas dispara el titular 'Amazing Things You Need'?", {"detect_clickbait_lexical"}),
    ("ESPECIFICA", "Muéstrame qué cues concretos aparecen en '10 Best Tips Ever' y dónde", {"detect_clickbait_lexical"}),
    ("ESPECIFICA", "Dame la probabilidad de clickbait de 'This Simple Trick Will Shock You'", {"detect_clickbait_linear"}),
    ("ESPECIFICA", "Usa el modelo entrenado para puntuar 'Doctors Hate This One Trick'", {"detect_clickbait_linear"}),
    ("ESPECIFICA", "¿El titular 'Cure Found' concuerda con el cuerpo 'Researchers report early-stage results in mice'?", {"detect_clickbait_incoherence"}),
    ("ESPECIFICA", "Compara titular y contenido: titular 'Miracle Diet Works', cuerpo 'A small study shows modest effects'", {"detect_clickbait_incoherence"}),
    ("ESPECIFICA", "¿Qué sentimiento transmite 'This is the worst day ever'?", {"analyze_sentiment"}),
    ("ESPECIFICA", "Analiza el tono emocional de 'A wonderful celebration took place'", {"analyze_sentiment"}),

    ("OTRO_DOMINIO", "Dame noticias del New York Times sobre inteligencia artificial", {"get_nyt_news"}),
    ("OTRO_DOMINIO", "¿Qué ha publicado The Guardian sobre cambio climático?", {"get_guardian_news"}),
    ("OTRO_DOMINIO", "¿Qué modelos usas y qué limitaciones tienen?", {"describe_models"}),

    ("SIN_TOOL", "¿Qué es el clickbait? Explícamelo en dos frases.", set()),
    ("SIN_TOOL", "Hola, ¿qué tal?", set()),
    ("SIN_TOOL", "Explícame cómo funciona una regresión logística", set()),
    ("SIN_TOOL", "¿Por qué es difícil detectar clickbait en español?", set()),
    ("SIN_TOOL", "Gracias, hasta luego", set()),
]

# Parámetros obligatorios por herramienta, para validar los argumentos.
OBLIGATORIOS = {
    t["function"]["name"]: set(t["function"]["parameters"]["required"]) for t in TOOLS
}


def chat(messages, tools=None, timeout=600):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": NUM_CTX},
    }
    if tools:
        payload["tools"] = tools
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    inicio = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as respuesta:
        datos = json.loads(respuesta.read())
    return datos, time.perf_counter() - inicio


def parametros_validos(nombre, argumentos):
    """¿Respeta el esquema? Requiere que estén los obligatorios y no vengan vacíos."""
    if nombre not in OBLIGATORIOS:
        return False, "herramienta inexistente"
    if not isinstance(argumentos, dict):
        return False, "argumentos no son un objeto"
    faltan = OBLIGATORIOS[nombre] - set(argumentos)
    if faltan:
        return False, f"faltan {sorted(faltan)}"
    vacios = [k for k in OBLIGATORIOS[nombre] if not str(argumentos.get(k, "")).strip()]
    if vacios:
        return False, f"vacíos {vacios}"
    return True, ""


if __name__ == "__main__":
    print(f"Modelo: {MODEL} | num_ctx: {NUM_CTX} | host: {OLLAMA_HOST} | "
          f"{len(TOOLS)} herramientas | {len(PRUEBAS)} consultas\n")

    por_categoria = Counter()
    aciertos_categoria = Counter()
    latencias = []
    params_ok = params_total = 0
    confusiones = Counter()

    for categoria, consulta, aceptables in PRUEBAS:
        try:
            datos, segundos = chat([{"role": "user", "content": consulta}], TOOLS)
        except urllib.error.URLError as error:
            print(f"ERROR de conexión: {error} — ¿está `ollama serve` en marcha?")
            raise SystemExit(1)

        mensaje = datos.get("message", {})
        llamadas = [
            (c.get("function", {}).get("name"), c.get("function", {}).get("arguments"))
            for c in (mensaje.get("tool_calls") or [])
        ]
        latencias.append(segundos)
        por_categoria[categoria] += 1

        elegidas = {n for n, _ in llamadas}
        if aceptables:
            correcto = bool(elegidas & aceptables)
        else:
            correcto = not elegidas
        aciertos_categoria[categoria] += correcto

        if not correcto and elegidas:
            for elegida in elegidas:
                confusiones[f"{sorted(aceptables)[0] if aceptables else 'ninguna'} -> {elegida}"] += 1

        for nombre, argumentos in llamadas:
            params_total += 1
            ok, _ = parametros_validos(nombre, argumentos)
            params_ok += ok

        marca = "OK " if correcto else "MAL"
        print(f"[{marca}] ({categoria}) {consulta[:72]}")
        if llamadas:
            for nombre, argumentos in llamadas:
                ok, motivo = parametros_validos(nombre, argumentos)
                aviso = "" if ok else f"   <-- PARÁMETROS: {motivo}"
                print(f"        -> {nombre}({json.dumps(argumentos, ensure_ascii=False)[:80]}){aviso}")
        else:
            print("        -> (sin llamada)")
        if not correcto:
            esperado = ", ".join(sorted(aceptables)) if aceptables else "NINGUNA"
            print(f"        esperado: {esperado}")
        print(f"        {segundos:.1f}s")

    print("\n" + "=" * 70)
    print("RESULTADOS")
    print("=" * 70)
    for categoria in ("GENERICA", "ESPECIFICA", "OTRO_DOMINIO", "SIN_TOOL"):
        total = por_categoria[categoria]
        if total:
            aciertos = aciertos_categoria[categoria]
            print(f"  {categoria:14s} {aciertos:2d}/{total:2d}  ({aciertos/total:5.0%})")
    total_global = sum(por_categoria.values())
    aciertos_global = sum(aciertos_categoria.values())
    print(f"  {'GLOBAL':14s} {aciertos_global:2d}/{total_global:2d}  ({aciertos_global/total_global:5.0%})")
    print()
    if params_total:
        print(f"  Parámetros válidos: {params_ok}/{params_total} ({params_ok/params_total:.0%})")
    print(f"  Latencia: media {sum(latencias)/len(latencias):.1f}s | "
          f"min {min(latencias):.1f}s | max {max(latencias):.1f}s")
    if confusiones:
        print("\n  Confusiones más frecuentes (esperada -> elegida):")
        for par, veces in confusiones.most_common(5):
            print(f"    {veces}x  {par}")
    print()
    print("  Criterio #82: acierto >= 80% y parámetros válidos casi siempre")
    print("  -> tool calling real. Por debajo -> modo guiado (R13.8).")
