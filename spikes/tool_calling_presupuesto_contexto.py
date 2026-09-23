"""Spike #82, rehecho en la A40 (2026-09-22) - ¿Cuánto contexto ocupa el catálogo?

La cifra que circulaba —unos 2.362 tokens— era una estimación. Aquí se mide con
el tokenizador del propio modelo: se manda una petición trivial con el catálogo
y otra sin él, y se lee `prompt_eval_count`, que es lo que el modelo dice haber
leído. La diferencia es lo que cuesta el catálogo.

Después se repite con varios `num_ctx`. Si el catálogo no cabe, **Ollama no da
error: recorta en silencio**, y `prompt_eval_count` sale por debajo del total.
Es lo que explicaba el 7/20 de la fase 5 con `num_ctx=2048`: el modelo elegía
entre las herramientas que le quedaban a la vista.

El catálogo se pide al servidor por `list_tools`, como en la fase 5, así que se
mide lo que hay en el código y no una copia. Por eso el resultado depende del
commit: cada docstring que crece lo cambia.

Ejecutar:  OLLAMA_HOST=127.0.0.1:11500 python spikes/tool_calling_presupuesto_contexto.py [modelo]
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spikes import tool_calling_fase5_descripciones_reales as fase5  # noqa: E402

CONTEXTOS = (2048, 4096, 8192, 16384)


def main() -> None:
    fase5.MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:27b"
    herramientas = asyncio.run(fase5.tools_del_servidor())

    print(f"modelo: {fase5.MODEL} | host: {fase5.OLLAMA_HOST}")
    print(f"{len(herramientas)} herramientas leídas del servidor\n")

    total_caracteres = 0
    por_nombre = sorted(
        herramientas, key=lambda candidata: candidata["function"]["name"]
    )
    for herramienta in por_nombre:
        funcion = herramienta["function"]
        descripcion = len(funcion["description"])
        esquema = len(json.dumps(funcion["parameters"], ensure_ascii=False))
        total_caracteres += descripcion + esquema
        print(
            f"  {funcion['name']:34} descripción {descripcion:5}  esquema {esquema:5}"
        )
    print(f"  {'TOTAL':34} {total_caracteres:>24} caracteres\n")

    pregunta = [{"role": "user", "content": "hola"}]

    # Con una ventana holgada, para que ninguna de las dos peticiones se recorte.
    fase5.NUM_CTX = 32768
    sin_catalogo, _ = fase5.chat(pregunta, [])
    con_catalogo, _ = fase5.chat(pregunta, herramientas)
    solo_plantilla = sin_catalogo["prompt_eval_count"]
    con_todo = con_catalogo["prompt_eval_count"]
    print(f"tokens de la petición SIN herramientas: {solo_plantilla}")
    print(f"tokens de la petición CON herramientas: {con_todo}")
    print(f"-> el catálogo cuesta {con_todo - solo_plantilla} tokens\n")

    for contexto in CONTEXTOS:
        fase5.NUM_CTX = contexto
        datos, _ = fase5.chat(pregunta, herramientas)
        leidos = datos["prompt_eval_count"]
        cabe = "cabe" if con_todo <= contexto else "NO CABE: se recorta sin avisar"
        print(f"  num_ctx {contexto:6} -> prompt_eval_count {leidos:6}  ({cabe})")


if __name__ == "__main__":
    main()
