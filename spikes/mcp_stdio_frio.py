"""#267 (2026-10-14) - El servidor por stdio, con y sin precalentado.

Lanza el servidor MCP como lo lanza Claude Desktop, como un subproceso que
habla por la entrada y la salida estándar, y mide lo que ve el cliente: cuánto
tarda el saludo (`initialize`) y cuánto el primer `analyze_headline`. Con
`PREHEAT_MODELS=true` la carga de los modelos pasa de la primera llamada al
saludo (#267).

Dos vías, las dos de la guía:
- `venv`: el `.venv` de esta copia (`docs/desarrollo.md`), con el `.env` de la
  raíz;
- `docker`: la imagen `clickbait-backend` ya construida (`docs/ejecucion.md`),
  con `docker run -i` y el `.env` de la raíz por `--env-file`.

No es Claude Desktop: sin su tiempo de espera ni el arranque de WSL. Para lo
que ve Desktop está `spikes/claude_desktop_registro.py`.

Desde que el precalentado va en un hilo (#267), el saludo ya no espera a los
modelos, y un análisis pedido nada más saludar espera lo que le falte a la
carga. El tercer argumento, opcional, son los segundos que se espera antes de
pedirlo: el caso de quien abre Claude Desktop y pregunta un rato después.

Ejecutar desde la raíz, en WSL:
    .venv/bin/python spikes/mcp_stdio_frio.py venv true
    .venv/bin/python spikes/mcp_stdio_frio.py docker false
    .venv/bin/python spikes/mcp_stdio_frio.py docker true 60
"""

import asyncio
import os
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RAIZ = Path(__file__).resolve().parent.parent

# El titular de la prueba de #267, con un cuerpo para que se ejecuten las cinco
# señales y se carguen todos los modelos del inglés.
TITULAR = "You Won't Believe What This Celebrity Did Next"
CUERPO = "The actor attended a charity gala on Saturday."


def parametros(via: str, precalentar: str) -> StdioServerParameters:
    if via == "docker":
        return StdioServerParameters(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "--env-file", str(RAIZ / ".env"),
                "-e", f"PREHEAT_MODELS={precalentar}",
                "clickbait-backend", "python", "-m", "backend.main",
            ],
        )
    return StdioServerParameters(
        command=str(RAIZ / ".venv/bin/python"),
        args=["-m", "backend.main"],
        env=dict(os.environ, PREHEAT_MODELS=precalentar),
        cwd=str(RAIZ),
    )


async def medir(via: str, precalentar: str, espera: float) -> None:
    inicio = time.perf_counter()
    async with stdio_client(parametros(via, precalentar)) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            await sesion.initialize()
            saludo = time.perf_counter() - inicio
            herramientas = await sesion.list_tools()
            await asyncio.sleep(espera)
            antes = time.perf_counter()
            resultado = await sesion.call_tool(
                "analyze_headline", {"headline": TITULAR, "content": CUERPO}
            )
            llamada = time.perf_counter() - antes
    veredicto = resultado.structuredContent.get("verdict") if resultado.structuredContent else None
    print(
        f"{via} PREHEAT_MODELS={precalentar}: {len(herramientas.tools)} herramientas, "
        f"saludo {saludo:.1f} s, primer analyze_headline {llamada:.1f} s "
        f"(pedido {espera:.0f} s después), veredicto {veredicto}",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(medir(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0))
