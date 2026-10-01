"""#188 (2026-09-26) - Dónde se van los tokens del catálogo que lee el agente.

La A40 midió el catálogo entero —2.929 tokens con las 12 herramientas, 2.846
quitando la sangría (`spikes/agente_a40.py`)—, pero no por herramienta ni por
sección del docstring. Esto lo reparte, sin GPU: pide el catálogo al `mcp` de
`backend.main` en proceso y mide en CARACTERES lo que se envía de cada
herramienta, descripción y esquema. Los tokens por herramienta son esos 2.929
repartidos en proporción, así que son una ESTIMACIÓN; el total sí está medido.

Responde a la pregunta de si recortar los docstrings aliviaría la ventana, y
qué parte se puede quitar sin cambiar lo que dicen: la sangría del docstring,
que FastMCP manda tal cual.

Ejecutar desde la raíz: NLP_BACKEND=local .venv/bin/python spikes/catalogo_peso.py
"""

import asyncio
import inspect
import json
import logging
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.mcp import session as mcp_session  # noqa: E402
from backend.core.mcp import tools  # noqa: E402
from backend.main import mcp as SERVIDOR  # noqa: E402

for ruidoso in ("httpx", "mcp"):
    logging.getLogger(ruidoso).setLevel(logging.WARNING)

TOKENS_MEDIDOS = 2929  # el catálogo de 12, con sangría (A40, 2026-09-26)
_BASE = "http://127.0.0.1:8765"


def _seccion(texto: str, nombre: str) -> int:
    """Caracteres de una sección del docstring, desde su cabecera hasta la siguiente."""
    encontrada = re.search(rf"^{nombre}:.*?(?=^\w+:\s*$|\Z)", texto, flags=re.M | re.S)
    return len(encontrada.group(0)) if encontrada else 0


async def main() -> None:
    app = SERVIDOR.streamable_http_app()
    async with app.router.lifespan_context(app):
        mcp_session._http_client = lambda corte: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE, timeout=corte
        )
        (catalogo,) = await tools.discover_all([f"{_BASE}/mcp"], 10.0)
    if isinstance(catalogo, BaseException):
        raise catalogo

    filas = [
        (
            herramienta.name,
            herramienta.description or "",
            len(json.dumps(herramienta.inputSchema, ensure_ascii=False)),
        )
        for herramienta in catalogo.tools
    ]
    total = sum(len(descripcion) + esquema for _, descripcion, esquema in filas)

    print(f"{len(filas)} herramientas · {total} caracteres entre descripciones y esquemas\n")
    print(f"{'herramienta':30} {'descripción':>11} {'esquema':>8} {'~tokens':>8}")
    for nombre, descripcion, esquema in sorted(filas, key=lambda fila: -(len(fila[1]) + fila[2])):
        parte = len(descripcion) + esquema
        print(f"{nombre:30} {len(descripcion):11} {esquema:8} {parte / total * TOKENS_MEDIDOS:8.0f}")

    descripciones = [descripcion for _, descripcion, _ in filas]
    crudas = sum(len(descripcion) for descripcion in descripciones)
    limpias = [inspect.cleandoc(descripcion) for descripcion in descripciones]
    print(f"\nDescripciones: {crudas} caracteres")
    print(f"  sangría y espacios de sobra: {crudas - sum(map(len, limpias))} ({(crudas - sum(map(len, limpias))) / crudas:.0%})")
    for nombre in ("Args", "Returns", "Raises"):
        caracteres = sum(_seccion(limpia, nombre) for limpia in limpias)
        print(f"  {nombre + ':':9} {caracteres} ({caracteres / crudas:.0%})")


if __name__ == "__main__":
    asyncio.run(main())
