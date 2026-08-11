"""Spike #82 - Fase 5: revalidar la selección con las descripciones REALES.

Motivo: al cambiar el contrato de retorno (#100) los docstrings pasaron de
prometer «devuelve un mensaje de error si falla» a declarar una sección
``Raises:``. Y el docstring **es la interfaz que lee el LLM**, así que había que
comprobar que el modelo sigue eligiendo igual.

Al ir a ejecutar la Fase 2 apareció que **no servía para esto**: dice usar «las
descripciones REALES (docstrings de tool.py)» pero las lleva copiadas a mano,
resumidas en dos o tres líneas. Medía unos textos que no habían cambiado.

Aquí las descripciones se piden al servidor por ``list_tools``, igual que hará
el agente en producción. Dos consecuencias: lo que se mide es lo que hay, y el
spike **no puede volver a desfasarse** del código.

Se reutilizan las 20 consultas y el criterio de acierto de la Fase 2, para que
las cifras sean comparables.

Ejecutar:  OLLAMA_HOST=127.0.0.1:11435 python spikes/tool_calling_fase5_descripciones_reales.py [modelo] [num_ctx]
"""

import asyncio
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP

# El spike vive fuera de los paquetes del proyecto; se añade la raíz al path
# para poder leer las herramientas reales sin convertir spikes/ en paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core import health  # noqa: E402
from backend.integrations.discovery import discover_and_register  # noqa: E402
from spikes.tool_calling_fase2 import PRUEBAS, parametros_validos  # noqa: E402

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
OLLAMA_URL = f"http://{OLLAMA_HOST}/api/chat"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:2b"
NUM_CTX = int(sys.argv[2]) if len(sys.argv) > 2 else 2048

_BASE = "http://127.0.0.1:8765"


async def tools_del_servidor() -> list[dict]:
    """Pide el catálogo al servidor real y lo traduce al formato de Ollama.

    Se habla el protocolo contra la app en el mismo proceso (``ASGITransport``):
    sin puertos ni subprocesos, pero con las descripciones y los esquemas
    exactos que recibirá el agente.

    El ``inputSchema`` de MCP ya es JSON Schema, y `parameters` de Ollama
    también, así que pasa tal cual.
    """
    mcp = FastMCP("tfg-mcp-server")
    discover_and_register(mcp)
    health.register(mcp)
    app = mcp.streamable_http_app()

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE
        ) as cliente,
        streamable_http_client(f"{_BASE}/mcp", http_client=cliente) as (r, w, _),
        ClientSession(r, w) as sesion,
    ):
        await sesion.initialize()
        listado = await sesion.list_tools()

    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema,
            },
        }
        for t in listado.tools
    ]


def chat(messages, tools, timeout=600):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": NUM_CTX},
        "tools": tools,
    }
    peticion = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    inicio = time.perf_counter()
    with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
        datos = json.loads(respuesta.read())
    return datos, time.perf_counter() - inicio


def main():
    tools = asyncio.run(tools_del_servidor())
    largos = [len(t["function"]["description"]) for t in tools]

    print(f"Modelo: {MODEL} | num_ctx: {NUM_CTX} | host: {OLLAMA_HOST}")
    print(f"{len(tools)} herramientas leídas del servidor por list_tools")
    print(f"Descripción media: {sum(largos) // len(largos)} caracteres "
          f"(la Fase 2 usaba resúmenes de ~150)\n")

    por_categoria = Counter()
    aciertos = Counter()
    latencias = []
    params_ok = params_total = 0
    fallos = []

    for categoria, consulta, aceptables in PRUEBAS:
        datos, segundos = chat([{"role": "user", "content": consulta}], tools)
        latencias.append(segundos)

        llamadas = datos.get("message", {}).get("tool_calls") or []
        elegidas = {c.get("function", {}).get("name") for c in llamadas}

        # Sin tools esperadas, acertar es NO llamar a ninguna.
        acierto = (not elegidas) if not aceptables else bool(elegidas & aceptables)

        por_categoria[categoria] += 1
        aciertos[categoria] += int(acierto)
        if not acierto:
            fallos.append((categoria, consulta[:52], sorted(elegidas) or "(ninguna)"))

        for llamada in llamadas:
            funcion = llamada.get("function", {})
            valido, _ = parametros_validos(
                funcion.get("name"), funcion.get("arguments") or {}
            )
            params_total += 1
            params_ok += int(valido)

        print(f"  {'OK ' if acierto else 'FALLO'} {categoria:13s} "
              f"{segundos:5.1f}s  {sorted(elegidas) or '-'}")

    print("\n--- Selección por categoría ---")
    for categoria in ["GENERICA", "ESPECIFICA", "OTRO_DOMINIO", "SIN_TOOL"]:
        if por_categoria[categoria]:
            print(f"  {categoria:13s} {aciertos[categoria]}/{por_categoria[categoria]}")
    total = sum(aciertos.values())
    print(f"  {'TOTAL':13s} {total}/{sum(por_categoria.values())}")

    if params_total:
        print(f"\nParámetros válidos: {params_ok}/{params_total}")

    latencias.sort()
    print(f"Latencia: mediana {latencias[len(latencias) // 2]:.1f}s | "
          f"min {latencias[0]:.1f}s | max {latencias[-1]:.1f}s")

    if fallos:
        print("\n--- Fallos ---")
        for categoria, consulta, elegidas in fallos:
            print(f"  {categoria:13s} {consulta!r} -> {elegidas}")


if __name__ == "__main__":
    main()
