"""#260 (2026-10-13) - El catálogo de herramientas, volcado para compararlo.

Subir `mcp` o `fastmcp` (lo pidió el análisis de vulnerabilidades) puede
cambiar lo que el agente le manda al modelo sin tocar una línea nuestra: la
descripción sale del docstring y el esquema lo genera FastMCP. Y un cambio en
eso exige las 26 consultas de `spikes/agente_a40.py`. Este guion vuelca el
catálogo antes y después de subir, para compararlos con `diff`:

- `agente`: lo que `backend/agent/agente.py` manda al modelo de cada
  herramienta —nombre, descripción con `inspect.cleandoc` y `inputSchema` como
  parámetros—, montado igual que allí. Si esto sale idéntico, el modelo recibe
  lo mismo y no hacen falta las 26 consultas.
- `resto`: lo demás que publica el catálogo (`title`, `outputSchema`,
  `annotations`), que leen `/tools` y la pantalla. Un cambio aquí no pide las
  26 consultas (#93), pero se mira.

Pide el catálogo al `mcp` de `backend.main` en proceso, sin red, como
`catalogo_peso.py`. Escribe JSON ordenado, para que `diff` sólo enseñe cambios
de verdad.

Ejecutar desde la raíz:
    NLP_BACKEND=local .venv/bin/python spikes/catalogo_volcado.py <salida.json>
"""

import asyncio
import inspect
import json
import logging
import sys
from importlib.metadata import version
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.mcp import session as mcp_session  # noqa: E402
from backend.core.mcp import tools  # noqa: E402
from backend.main import mcp as SERVIDOR  # noqa: E402

for ruidoso in ("httpx", "mcp"):
    logging.getLogger(ruidoso).setLevel(logging.WARNING)

_BASE = "http://127.0.0.1:8765"


async def _catalogo():
    app = SERVIDOR.streamable_http_app()
    async with app.router.lifespan_context(app):
        mcp_session._http_client = lambda corte: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE, timeout=corte
        )
        (catalogo,) = await tools.discover_all([f"{_BASE}/mcp"], 10.0)
    if isinstance(catalogo, BaseException):
        raise catalogo
    return catalogo


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    salida = Path(sys.argv[1])
    catalogo = asyncio.run(_catalogo())

    volcado = {
        "versiones": {paquete: version(paquete) for paquete in ("mcp", "fastmcp", "starlette")},
        "agente": {
            herramienta.name: {
                "name": herramienta.name,
                "description": inspect.cleandoc(herramienta.description or ""),
                "parameters": herramienta.inputSchema,
            }
            for herramienta in catalogo.tools
        },
        "resto": {
            herramienta.name: {
                "title": herramienta.title,
                "outputSchema": herramienta.outputSchema,
                "annotations": (
                    herramienta.annotations.model_dump(exclude_none=True)
                    if herramienta.annotations
                    else None
                ),
            }
            for herramienta in catalogo.tools
        },
    }
    salida.write_text(json.dumps(volcado, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"{len(catalogo.tools)} herramientas, {volcado['versiones']}, en {salida}")


if __name__ == "__main__":
    main()
