"""#196 (2026-09-26) - Por qué `get_guardian_news` no encuentra nada con tema.

En la aceptación de #188, los cuatro temas que probó el agente —«climate
change», «climate», «weather» y «extreme weather»— dieron «No articles found»,
y sin tema sí llegaron noticias. Leyendo el código salen dos hipótesis que,
desde fuera, dan el mismo mensaje:

1. La etiqueta: `search_articles` resuelve el tema a una etiqueta con
   `_find_tag` (#47) y busca SÓLO por ella; si esa etiqueta no tiene nada en la
   ventana, no vuelve a probar con la búsqueda libre `q=`.
2. Un fallo de la petición: si `/search` falla por lo que sea —un 429, un 401,
   un timeout—, el cliente también lo devuelve como «No articles found». Con
   tema son dos peticiones seguidas (`/tags` y `/search`); sin tema, una.

Para cada tema se mide, con el `GuardianAPI` de producción —la subclase sólo
anota lo que pasa por `make_request`, sin cambiar nada de lo que hace—:

- `search_articles(tema, 7)` tal cual, que es lo que ve el agente: qué
  etiquetas devolvió `/tags`, cuál eligió `_find_tag` y qué contestó `/search`;
- tras una pausa, `/search` con esa misma etiqueta: si ahora trae algo, es el
  ritmo y no la etiqueta;
- `/search` con `q=` en la misma ventana;
- y los tres primeros titulares de cada variante, para juzgar el criterio de
  #47 («intelligence» traía espías y música).

La columna de producción da lo que devolvió `search_articles` y el camino de
búsquedas que hizo: `ok, 10 (tag 0 → q 391)` es que la etiqueta no trajo nada
y volvió a `q=`, que es el arreglo de #196.

Cuesta 4 llamadas por tema —5 si vuelve a `q=`—, de 32 a 40 en total, de las
500 diarias de la clave. La
clave no se imprime: se tapa en todo lo que se escribe, y el registro de
`make_request` se captura en vez de salir por pantalla.

Ejecutar desde la raíz: .venv/bin/python spikes/guardian_temas.py
(el JSON va a GUARDIAN_TEMAS_JSON, por defecto /tmp/guardian_temas.json).
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from structlog.testing import capture_logs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config.settings import settings
from backend.core.models import ToolResult
from backend.integrations.guardian.client import GuardianAPI

# El INFO de httpx escribe la URL de cada petición, y la clave va en la URL.
logging.getLogger("httpx").setLevel(logging.WARNING)

TEMAS_DE_188 = ["climate change", "climate", "weather", "extreme weather"]
TEMAS_DE_CONTROL = ["technology", "artificial intelligence", "intelligence", "politics"]
DIAS = 7  # el defecto de la herramienta, y lo que mandó el agente
PAUSA_S = 2.0
SALIDA = Path(os.environ.get("GUARDIAN_TEMAS_JSON", "/tmp/guardian_temas.json"))


class GuardianAnotado(GuardianAPI):
    """El cliente de producción, anotando cada petición que hace."""

    def __init__(self) -> None:
        super().__init__()
        self.peticiones: list[dict[str, Any]] = []

    async def make_request(
        self,
        endpoint: str,
        method: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> ToolResult:
        # Copia: `make_request` mete la clave en el diccionario que recibe.
        enviados = {
            nombre: str(valor)
            for nombre, valor in (params or {}).items()
            if nombre != self.API_KEY_PARAM
        }
        respuesta = await super().make_request(
            endpoint, method, dict(params or {}), json
        )
        cuerpo = (
            respuesta.unwrap().get("response", {}) if respuesta.has_content() else {}
        )
        resultados = cuerpo.get("results") or []
        self.peticiones.append(
            {
                "endpoint": endpoint,
                "params": enviados,
                "ok": respuesta.success,
                "error": respuesta.error,
                "total": cuerpo.get("total"),
                "ids": [etiqueta.get("id") for etiqueta in resultados]
                if endpoint == "tags"
                else None,
                "titulares": [articulo.get("webTitle") for articulo in resultados[:3]]
                if endpoint == "search"
                else None,
            }
        )
        return respuesta


def _tapar(valor: Any) -> Any:
    """Quita la clave de cualquier cosa que se vaya a escribir."""
    texto = json.dumps(valor, ensure_ascii=False, default=str)
    if settings.guardian_api_key:
        texto = texto.replace(settings.guardian_api_key, "***")
    return json.loads(texto)


def _celda(peticion: dict[str, Any] | None) -> str:
    if peticion is None:
        return "—"
    if peticion["ok"]:
        return f"total {peticion['total']}"
    return f"ERROR {peticion['error']}"


def _camino(produccion: dict[str, Any]) -> str:
    """Lo que devolvió `search_articles` y las búsquedas que hizo para ello:
    `ok, 10 (tag 0 → q 391)` es que la etiqueta no trajo nada y volvió a `q=`."""
    pasos = " → ".join(
        ("tag" if "tag" in busqueda["params"] else "q") + f" {busqueda['total']}"
        if busqueda["ok"]
        else "ERROR"
        for busqueda in produccion["busquedas"]
    )
    estado = f"ok, {produccion['articulos']}" if produccion["ok"] else "FALLA"
    return f"{estado} ({pasos})"


async def _buscar(api: GuardianAnotado, **filtro: str) -> dict[str, Any]:
    """Una búsqueda con la misma ventana y los mismos campos que la de producción."""
    desde = datetime.now(UTC).date() - timedelta(days=DIAS)
    params = {"from-date": desde, "show-fields": "trailText", **filtro}
    await api.make_request("search", "get", params)
    return api.peticiones[-1]


async def _medir(api: GuardianAnotado, tema: str) -> dict[str, Any]:
    inicio = len(api.peticiones)
    resultado = await api.search_articles(tema, DIAS)
    produccion = api.peticiones[inicio:]
    etiquetas = next((p["ids"] for p in produccion if p["endpoint"] == "tags"), None)
    busquedas = [p for p in produccion if p["endpoint"] == "search"]
    elegida = busquedas[0]["params"].get("tag") if busquedas else None

    fila: dict[str, Any] = {
        "tema": tema,
        "etiquetas": etiquetas,
        "elegida": elegida,
        "produccion": {
            "ok": resultado.success,
            "error": resultado.error,
            "articulos": len(resultado.unwrap()) if resultado.success else 0,
            # Todas las búsquedas, en orden: la última es la que devuelve.
            "busquedas": busquedas,
        },
        "etiqueta_con_pausa": None,
    }
    await asyncio.sleep(PAUSA_S)
    if elegida:
        fila["etiqueta_con_pausa"] = await _buscar(api, tag=elegida)
        await asyncio.sleep(PAUSA_S)
    fila["libre"] = await _buscar(api, q=tema)
    return fila


def _commit() -> str:
    raiz = Path(__file__).resolve().parent.parent
    corto = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        cwd=raiz,
    ).stdout.strip()
    sucio = subprocess.run(
        ["git", "status", "--porcelain", "backend"],
        capture_output=True,
        text=True,
        cwd=raiz,
    ).stdout.strip()
    return f"{corto}{' (backend/ con cambios sin commitear)' if sucio else ''}"


async def main() -> dict[str, Any]:
    api = GuardianAnotado()
    fecha = datetime.now(UTC)
    filas = []
    with capture_logs() as registrado:
        for tema in TEMAS_DE_188 + TEMAS_DE_CONTROL:
            filas.append(await _medir(api, tema))
            await asyncio.sleep(PAUSA_S)

    print(f"fecha: {fecha.isoformat(timespec='seconds')} · commit: {_commit()}")
    print(f"ventana: {DIAS} días, desde {fecha.date() - timedelta(days=DIAS)}")
    print(
        f"llamadas: {api.call_count} · cuota diaria restante: {api.remaining_quota}\n"
    )
    print(
        f"{'tema':24} {'etiqueta elegida':46} {'producción':26} {'etiqueta tras pausa':20} q="
    )
    for fila in filas:
        print(
            f"{fila['tema']:24} {fila['elegida']!s:46} {_camino(fila['produccion']):26} "
            f"{_celda(fila['etiqueta_con_pausa']):20} {_celda(fila['libre'])}"
        )

    for fila in filas:
        busquedas = fila["produccion"]["busquedas"]
        print(f"\n== {fila['tema']}")
        print(f"  /tags: {(fila['etiquetas'] or [])[:6]}")
        for nombre, peticion in (
            ("producción", busquedas[-1] if busquedas else None),
            ("etiqueta tras pausa", fila["etiqueta_con_pausa"]),
            ("q=", fila["libre"]),
        ):
            if peticion and peticion["titulares"]:
                print(f"  {nombre}: {peticion['titulares']}")

    avisos = [evento for evento in registrado if evento.get("log_level") != "info"]
    print(f"\navisos de make_request: {len(avisos)}")
    for evento in avisos:
        print(" ", _tapar(evento))

    return {
        "fecha": fecha.isoformat(timespec="seconds"),
        "commit": _commit(),
        "dias": DIAS,
        "llamadas": api.call_count,
        "cuota_restante": api.remaining_quota,
        "filas": filas,
        "avisos": avisos,
    }


if __name__ == "__main__":
    medida = asyncio.run(main())
    SALIDA.write_text(
        json.dumps(_tapar(medida), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nJSON: {SALIDA}")
