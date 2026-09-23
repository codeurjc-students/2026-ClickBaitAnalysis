"""Spike #82, rehecho en la A40 (2026-09-22) - ¿Cuánto cuesta cargar un modelo?

En la GTX 1650 la primera consulta tardó 150,6 s, y ese número sostenía que el
chat no pudiera ser una petición bloqueante. Hay que saber cuánto es aquí.

Se lee `load_duration` de la respuesta de Ollama, que **separa la carga de la
generación**. Cronometrar la petición entera las confunde: la primera medida de
este spike se descartó por eso, y porque además los modelos seguían en la VRAM.
`num_predict=1` para que generar no pese nada.

Por cada modelo: se saca de la VRAM (`keep_alive: 0` en una petición vacía, que
es como lo documenta Ollama) y se hacen dos peticiones. La primera paga la
carga; la segunda debe salir en cero.

Ojo con cómo se lee el resultado. Un servidor recién arrancado paga una vez el
calentamiento de CUDA (~8 s, visto el 2026-09-22), y lo paga **la primera
petición que recibe**. Aquí esa es la que saca el modelo de la VRAM, así que
ese coste no llega a la tabla y lo medido es sólo la carga del modelo.
Cronometrar a mano la primera petición tras arrancar daría esos segundos de más
—es lo que pasó en la primera tanda, y de ahí sale el «15 s» del README—.

Y siempre con la caché de disco CALIENTE: tras reiniciar la máquina, leer los
pesos cuesta más, y eso no lo mide este script. Tampoco es una cifra fija: el
2B cargó en 6,8 s el 2026-09-22 y en 3,1 s el 23, con el mismo servidor.

Ejecutar:  OLLAMA_HOST=127.0.0.1:11500 python spikes/tool_calling_carga.py [modelo ...]
"""

import json
import os
import sys
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
MODELOS = sys.argv[1:] or ["qwen3.5:2b", "qwen3.5:27b"]
NUM_CTX = 8192


def pedir(ruta: str, cuerpo: dict, timeout: int = 900) -> dict:
    peticion = urllib.request.Request(
        f"http://{OLLAMA_HOST}{ruta}",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
        return json.loads(respuesta.read())


def sacar_de_la_vram(modelo: str) -> None:
    pedir("/api/generate", {"model": modelo, "keep_alive": 0})


def medir(modelo: str) -> tuple[float, float, float]:
    """Segundos de carga, de lectura del prompt y totales de una petición mínima."""
    datos = pedir(
        "/api/chat",
        {
            "model": modelo,
            "stream": False,
            "options": {"num_ctx": NUM_CTX, "num_predict": 1},
            "messages": [{"role": "user", "content": "hola"}],
        },
    )
    en_segundos = 1e9  # Ollama da las duraciones en nanosegundos
    return (
        datos.get("load_duration", 0) / en_segundos,
        datos.get("prompt_eval_duration", 0) / en_segundos,
        datos.get("total_duration", 0) / en_segundos,
    )


def main() -> None:
    print(f"host: {OLLAMA_HOST} | num_ctx: {NUM_CTX}\n")
    for modelo in MODELOS:
        sacar_de_la_vram(modelo)
        for orden in ("1.ª", "2.ª"):
            carga, prompt, total = medir(modelo)
            print(
                f"  {modelo:14} {orden} petición   carga {carga:6.1f} s | "
                f"prompt {prompt:5.2f} s | total {total:6.1f} s"
            )


if __name__ == "__main__":
    main()
