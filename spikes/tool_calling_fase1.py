"""Spike #82 - Fase 1: ¿el modelo local hace tool calling?

Prueba MÍNIMA: una sola herramienta y un esquema simple. Es el filtro de entrada:
si el modelo no llama bien a UNA tool, no tiene sentido medir las fases 2 y 3.

Se comprueban dos cosas opuestas, porque fallar en cualquiera invalida al modelo:
  1. Que LLAME a la herramienta cuando hace falta.
  2. Que NO la llame cuando la pregunta no la necesita (los modelos pequeños
     tienden a invocar tools por inercia en cuanto se les ofrece una).

Requisitos: `ollama serve` en marcha y el modelo descargado.
Ejecutar:   python spikes/tool_calling_fase1.py [modelo]

El modelo se pasa por argumento porque comparar tamaños ES el objetivo: en una
GPU de 4 GB, un modelo que no quepa se ejecuta 100% en CPU y la latencia lo hace
inservible (comprobado con qwen3.5:4b -> 5.4 GiB -> 0/33 capas en GPU).
"""

import json
import sys
import time
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:2b"

# La caché KV crece con el contexto y compite con los pesos por la VRAM. En una
# GPU de 4 GB es la palanca más barata para que el modelo quepa: con num_ctx=4096
# hacen falta ~3.8 GiB (no cabe -> 100% CPU -> ~64 s por respuesta).
NUM_CTX = int(sys.argv[2]) if len(sys.argv) > 2 else 2048

# Esquema de la herramienta en el formato que espera Ollama (estilo OpenAI).
# OJO: en el sistema real esto NO se escribe a mano — FastMCP lo genera a partir
# del docstring + los type hints, y el agente lo recibe por MCP (tools/list).
# Aquí se replica el texto real de `detect_clickbait_lexical` para que el spike
# mida el comportamiento del modelo con NUESTRAS descripciones, no con un ejemplo
# de juguete.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "detect_clickbait_lexical",
            "description": (
                "Detecta clickbait por pistas léxicas y estructurales del titular "
                "(hipérbole, referencias vagas, número inicial, interrogación, "
                "mayúsculas, elipsis) y devuelve qué pistas dispararon y dónde. "
                "Pensada para titulares en inglés."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "headline": {
                        "type": "string",
                        "description": "Titular a evaluar (en inglés).",
                    }
                },
                "required": ["headline"],
            },
        },
    }
]

# (consulta, ¿debería llamar a la tool?)
PRUEBAS = [
    ("¿Es clickbait este titular? '10 Amazing Things You Won't Believe'", True),
    ("Analiza: 'Spain wins the 2026 World Cup'", True),
    ("¿Qué es el clickbait? Explícamelo en dos frases.", False),
    ("Hola, ¿qué tal?", False),
]


def chat(messages, tools=None, timeout=300):
    """Una llamada a /api/chat. Devuelve (respuesta, segundos).

    stream=False para recibir la respuesta completa de una vez; en el backend
    real interesará streaming, pero aquí sólo se mide comportamiento.
    """
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


def _resumen_llamadas(mensaje):
    """Extrae las tool_calls de la respuesta -> lista de (nombre, argumentos)."""
    llamadas = []
    for llamada in mensaje.get("tool_calls") or []:
        funcion = llamada.get("function", {})
        llamadas.append((funcion.get("name"), funcion.get("arguments")))
    return llamadas


if __name__ == "__main__":
    print(f"Modelo: {MODEL} | num_ctx: {NUM_CTX}\n")

    aciertos = 0
    latencias = []

    for consulta, espera_llamada in PRUEBAS:
        try:
            datos, segundos = chat([{"role": "user", "content": consulta}], TOOLS)
        except urllib.error.URLError as error:
            print(f"ERROR de conexión con Ollama: {error}")
            print("¿Está corriendo `ollama serve`?")
            raise SystemExit(1)

        mensaje = datos.get("message", {})
        llamadas = _resumen_llamadas(mensaje)
        latencias.append(segundos)

        llamo = bool(llamadas)
        correcto = llamo == espera_llamada
        aciertos += correcto

        print(f"[{'OK ' if correcto else 'MAL'}] {consulta}")
        print(f"      esperado: {'llamar' if espera_llamada else 'NO llamar':10s}"
              f" | obtenido: {'llamó' if llamo else 'no llamó':10s} | {segundos:5.1f}s")
        for nombre, argumentos in llamadas:
            print(f"      -> {nombre}({argumentos})")
        if not llamo:
            texto = (mensaje.get("content") or "").strip().replace("\n", " ")
            print(f"      texto: {texto[:110]}...")
        print()

    total = len(PRUEBAS)
    print(f"Aciertos de decisión: {aciertos}/{total}")
    print(f"Latencia media: {sum(latencias)/len(latencias):.1f}s "
          f"(min {min(latencias):.1f}s, max {max(latencias):.1f}s)")
    print()
    print("Criterio de la Fase 1: si no llama cuando debe, o llama siempre,")
    print("el modelo no sirve para tool calling -> plan B (modo guiado, R13.8).")
