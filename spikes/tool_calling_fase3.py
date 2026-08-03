"""Spike #82 - Fase 3: el bucle completo del agente (encadenamiento).

Las fases 1 y 2 sólo medían SI el modelo elige bien la herramienta. Nunca se
ejecutó una tool ni se le devolvió el resultado. Aquí se prueba el bucle entero,
que es lo que hará el chat en producción:

    consulta -> el modelo pide una tool -> SE EJECUTA de verdad
             -> se le devuelve el resultado (role="tool")
             -> el modelo lo usa y responde, o pide otra tool

Lo que se quiere ver:
  - ¿Encadena? (usar la salida de una tool como entrada de la siguiente)
  - ¿USA los datos devueltos, o los ignora / se los inventa?  <- clave para R13.4
  - ¿Cuántas vueltas y cuánto tiempo cuesta una respuesta completa?

Las herramientas locales (léxico, lineal) se ejecutan REALES. La de noticias se
simula con un artículo fijo: así el experimento es determinista y no depende de
claves de API ni de la disponibilidad del NYT.

Ejecutar: OLLAMA_HOST=127.0.0.1:11435 python spikes/tool_calling_fase3.py [modelo]
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

# El spike vive fuera de los paquetes del proyecto; se añade la raíz al path
# para poder ejecutar las herramientas reales sin convertir spikes/ en paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.integrations.nlp import lexical, linear  # noqa: E402

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
OLLAMA_URL = f"http://{OLLAMA_HOST}/api/chat"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:2b"
NUM_CTX = int(sys.argv[2]) if len(sys.argv) > 2 else 4096  # el bucle acumula contexto
MAX_VUELTAS = 6  # cortafuegos: un agente que no converge no debe girar sin fin

# Artículo fijo que devuelve la tool de noticias simulada. El titular es
# deliberadamente sensacionalista para que el análisis posterior tenga sustancia.
ARTICULO = {
    "title": "This One AI Trick Will Completely Change Your Job Forever",
    "content": (
        "Researchers at a small lab published a preprint describing modest "
        "productivity gains when using an AI assistant for routine coding tasks. "
        "The study covered 40 participants over two weeks."
    ),
    "url": "https://www.nytimes.com/example",
    "date": "2026-08-01",
}


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
        "get_nyt_news",
        "Busca noticias del New York Times sobre un tema. Devuelve el titular, el "
        "contenido y la fecha de cada artículo.",
        {"topic": {"type": "string", "description": "Tema a buscar."}},
        ["topic"],
    ),
    _tool(
        "detect_clickbait_lexical",
        "Detecta clickbait por pistas léxicas y estructurales del titular: hipérbole, "
        "referencias vagas, número inicial, interrogación, mayúsculas, elipsis. "
        "Devuelve QUÉ pistas dispararon y DÓNDE.",
        _HEADLINE, ["headline"],
    ),
    _tool(
        "detect_clickbait_linear",
        "Detecta clickbait con un modelo lineal entrenado. Devuelve la PROBABILIDAD "
        "de clickbait y los cues que más contribuyeron, con su peso.",
        _HEADLINE, ["headline"],
    ),
]


def ejecutar(nombre, argumentos):
    """Ejecuta la herramienta de verdad y devuelve su salida (dict)."""
    argumentos = argumentos or {}
    if nombre == "get_nyt_news":
        return {"articles": [ARTICULO]}
    if nombre == "detect_clickbait_lexical":
        resultado = lexical.detect(argumentos.get("headline", ""))
    elif nombre == "detect_clickbait_linear":
        resultado = linear.predict(argumentos.get("headline", ""))
    else:
        return {"error": f"herramienta desconocida: {nombre}"}
    return resultado.data if resultado.success else {"error": resultado.error}


def chat(messages, tools, timeout=600):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": NUM_CTX},
        "tools": tools,
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    inicio = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as respuesta:
        return json.loads(respuesta.read()), time.perf_counter() - inicio


def bucle_agente(consulta, sistema=None):
    """El bucle de tool calling. Este es, en esencia, el agente real.

    `sistema` es el prompt de sistema (R13.5): se pasa como primer mensaje y por
    eso puede cambiarse por configuración sin tocar el bucle.
    """
    mensajes = []
    if sistema:
        mensajes.append({"role": "system", "content": sistema})
    mensajes.append({"role": "user", "content": consulta})
    traza = []
    total = 0.0

    for vuelta in range(MAX_VUELTAS):
        datos, segundos = chat(mensajes, TOOLS)
        total += segundos
        mensaje = datos.get("message", {})
        mensajes.append(mensaje)

        llamadas = mensaje.get("tool_calls") or []
        if not llamadas:
            return mensaje.get("content", ""), traza, total, vuelta + 1

        for llamada in llamadas:
            funcion = llamada.get("function", {})
            nombre = funcion.get("name")
            argumentos = funcion.get("arguments") or {}
            salida = ejecutar(nombre, argumentos)
            traza.append((nombre, argumentos, salida))
            # Se devuelve el resultado al modelo como un mensaje de rol "tool".
            mensajes.append({
                "role": "tool",
                "tool_name": nombre,
                "content": json.dumps(salida, ensure_ascii=False)[:1500],
            })

    return "(no convergió)", traza, total, MAX_VUELTAS


CONSULTAS = [
    # Encadenamiento real: la salida de una tool alimenta a la siguiente.
    "Busca una noticia del New York Times sobre inteligencia artificial y dime si su titular es clickbait.",
    # Dos herramientas distintas sobre el mismo titular.
    "Del titular 'This Simple Trick Will Shock You': dime qué pistas léxicas tiene y también su probabilidad según el modelo entrenado.",
]


if __name__ == "__main__":
    print(f"Modelo: {MODEL} | num_ctx: {NUM_CTX} | host: {OLLAMA_HOST}\n")

    for consulta in CONSULTAS:
        print("=" * 78)
        print(f"CONSULTA: {consulta}")
        print("=" * 78)

        respuesta, traza, segundos, vueltas = bucle_agente(consulta)

        print(f"\nTRAZA ({len(traza)} llamadas, {vueltas} vueltas al modelo, {segundos:.1f}s):")
        for i, (nombre, argumentos, salida) in enumerate(traza, 1):
            print(f"  {i}. {nombre}({json.dumps(argumentos, ensure_ascii=False)[:90]})")
            print(f"     -> {json.dumps(salida, ensure_ascii=False)[:150]}")

        print(f"\nRESPUESTA FINAL:\n{respuesta[:900]}\n")

    print("=" * 78)
    print("A revisar a mano (no se puede automatizar):")
    print("  - ¿Encadenó? (titular obtenido de la noticia -> pasado al detector)")
    print("  - ¿La respuesta USA los números de las tools, o se los inventa?")
    print("    Inventarlos confirmaría por qué el veredicto no puede salir del LLM (R13.4).")
