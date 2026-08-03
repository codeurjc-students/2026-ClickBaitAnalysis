"""Spike #82 - Fase 4: ¿cuánto cambia el comportamiento según el prompt de sistema?

La Fase 3 destapó dos problemas con el prompt por defecto (ninguno):
  1. Latencia alta (70-104 s por respuesta), porque el modelo redacta tablas
     largas con emojis en cada vuelta.
  2. Fabricación: transcribe bien los NÚMEROS de las herramientas, pero se
     inventa lo que los rodea (una escala «2 sobre 3» inexistente, explicaciones
     de los cues que ninguna tool ha dado, un nombre de empresa).

Como el prompt es configuración versionada (R13.5), comparar variantes ES el
experimento correcto. Se mide si el prompt puede suprimir ambos problemas.

Variantes en spikes/prompts/. La ausencia de prompt es el grupo de control.

Ejecutar: OLLAMA_HOST=127.0.0.1:11435 python spikes/tool_calling_fase4_prompts.py
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spikes.tool_calling_fase3 import CONSULTAS, bucle_agente  # noqa: E402

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def cargar_prompts():
    """(nombre, contenido) por variante. None = control sin prompt."""
    variantes = [("sin-prompt", None)]
    for ruta in sorted(PROMPTS_DIR.glob("*.md")):
        variantes.append((ruta.stem, ruta.read_text(encoding="utf-8")))
    return variantes


# Marcas automáticas. AVISO: la primera versión sólo buscaba escalas «/3» y «/5»
# -las vistas en la Fase 3- y por eso NO detectó un «score 2/1» que apareció
# después. Es la limitación del método: se construye con los fallos ya conocidos,
# y las invenciones nuevas adoptan formas nuevas. Sirve de cribado, no de prueba;
# la revisión manual sigue siendo obligatoria.
PATRONES_FABRICACION = [
    (r"\b\d+\s*/\s*\d+\b|\b\d+\s+sobre\s+\d+\b", "escala inventada (X/Y)"),
    (r"[\U0001F300-\U0001FAFF☀-➿]", "emojis"),
    (r"^\s*\|", "tablas"),
    (r"\*\*|__", "negritas"),
    (r"^\s*#{1,6}\s", "encabezados"),
    (r"^\s*[-*+]\s", "listas"),
    (r"\b(he|hemos)\s+(detectado|analizado|encontrado)\b|\bmi\s+análisis\b", "se atribuye el análisis"),
]


def cifras_sin_respaldo(texto, traza):
    """Números de la respuesta que NO aparecen en la salida de ninguna herramienta.

    Comprobación de fidelidad numérica: si el modelo menciona una probabilidad o
    una posición, debe venir de una tool. Tolera los conteos derivados (p. ej.
    «2 pistas» cuando hay dos matches) admitiendo números pequeños.
    NO detecta datos correctos mal atribuidos -como dar el span de una pista a
    otra-, que siguen requiriendo lectura manual.
    """
    salidas = " ".join(json.dumps(s, ensure_ascii=False) for _, _, s in traza)
    numeros_tool = set(re.findall(r"\d+", salidas))
    huerfanos = []
    for numero in re.findall(r"\d+(?:[.,]\d+)?", texto):
        entero = numero.replace(",", ".").split(".")[0]
        decimales = numero.replace(",", ".").replace(".", "")
        if entero in numeros_tool or decimales[:6] in salidas.replace(".", ""):
            continue
        if len(entero) <= 1:  # conteos y ordinales derivados
            continue
        huerfanos.append(numero)
    return huerfanos


def revisar(texto, traza=()):
    """Marcas automáticas de estilo/fabricación. Complementa la revisión manual."""
    hallazgos = []
    for patron, etiqueta in PATRONES_FABRICACION:
        if re.search(patron, texto, flags=re.MULTILINE):
            hallazgos.append(etiqueta)
    huerfanos = cifras_sin_respaldo(texto, traza)
    if huerfanos:
        hallazgos.append(f"cifras sin respaldo: {', '.join(huerfanos[:4])}")
    return hallazgos


if __name__ == "__main__":
    variantes = cargar_prompts()
    print(f"Variantes: {', '.join(n for n, _ in variantes)}")
    print(f"Consultas: {len(CONSULTAS)}\n")

    resumen = []

    for nombre, sistema in variantes:
        print("#" * 78)
        print(f"# PROMPT: {nombre}")
        print("#" * 78)

        for i, consulta in enumerate(CONSULTAS, 1):
            inicio = time.perf_counter()
            respuesta, traza, segundos, vueltas = bucle_agente(consulta, sistema)
            del inicio

            hallazgos = revisar(respuesta, traza)
            resumen.append({
                "prompt": nombre,
                "consulta": i,
                "segundos": segundos,
                "vueltas": vueltas,
                "llamadas": len(traza),
                "caracteres": len(respuesta),
                "marcas": hallazgos,
            })

            print(f"\n--- consulta {i} --- {segundos:.1f}s | {vueltas} vueltas | "
                  f"{len(traza)} tools | {len(respuesta)} chars")
            print("    tools:", " -> ".join(n for n, _, _ in traza) or "(ninguna)")
            if hallazgos:
                print("    MARCAS:", ", ".join(hallazgos))
            print(f"    respuesta: {respuesta[:400]}")
        print()

    print("=" * 78)
    print("RESUMEN")
    print("=" * 78)
    print(f"{'prompt':14s} {'seg':>7s} {'vueltas':>8s} {'tools':>6s} {'chars':>7s}  marcas")
    for fila in resumen:
        print(f"{fila['prompt']:14s} {fila['segundos']:7.1f} {fila['vueltas']:8d} "
              f"{fila['llamadas']:6d} {fila['caracteres']:7d}  {', '.join(fila['marcas']) or '-'}")

    print()
    print("Por variante (media de las consultas):")
    for nombre, _ in variantes:
        filas = [f for f in resumen if f["prompt"] == nombre]
        media_s = sum(f["segundos"] for f in filas) / len(filas)
        media_c = sum(f["caracteres"] for f in filas) / len(filas)
        con_marcas = sum(1 for f in filas if f["marcas"])
        print(f"  {nombre:14s} {media_s:6.1f}s | {media_c:6.0f} chars | "
              f"{con_marcas}/{len(filas)} respuestas con marcas")

    print()
    print("A revisar a mano: ¿siguen apareciendo interpretaciones inventadas de los")
    print("cues, o datos del artículo que no estaban en la salida de la herramienta?")
