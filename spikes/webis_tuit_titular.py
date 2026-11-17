"""En cuántos tuits de Webis-Clickbait-17 el texto difiere del titular del artículo.

16 nov 2026, PR #298. La memoria (capítulo 5, «Transformaciones») dice que el
texto del tuit, que es lo que leyeron los anotadores, difiere del titular del
artículo enlazado en el 75 % de los casos. Lo afirmaban el docstring de
`backend/evaluation/webis_extract.py` y `data/external/ATTRIBUTION.md`, pero
ningún guion lo calculaba. Éste lo cuenta en el trozo grande (`validation170630`),
cruzando por `id` los dos ficheros que deja `webis_extract`: el tuit, en el campo
`headline` del de titulares, y el titular del artículo, en `targetTitle` del de
cuerpos. Los dos viven en `var/webis/`, sin versionar.

Se cuenta de dos maneras: tal cual, y sin distinguir mayúsculas ni los espacios
repetidos, porque un tuit que sólo cambia la caja del titular no es otro texto.
Lo demás (comillas tipográficas, puntuación, emojis) cuenta como diferencia.

Ejecutar desde la raíz: .venv/bin/python spikes/webis_tuit_titular.py

Resultados (2026-11-16): de los 19.484 tuits con texto, el tuit difiere del
titular del artículo en 14.605 (75,0 %) sin contar mayúsculas ni espacios, y en
16.562 (85,0 %) tal cual. Ningún tuit ni ningún titular del artículo está vacío.
"""

import gzip
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TITULARES = RAIZ / "var" / "webis" / "webis17_validation170630.jsonl.gz"
CUERPOS = RAIZ / "var" / "webis" / "webis17_validation170630_cuerpos.jsonl.gz"

TUITS = 19_484


def _leer(ruta: Path) -> list[dict]:
    with gzip.open(ruta, "rt", encoding="utf-8") as fichero:
        return [json.loads(linea) for linea in fichero]


def _normalizar(texto: str) -> str:
    """Sin distinguir mayúsculas ni espacios repetidos."""
    return " ".join(texto.split()).casefold()


def _porcentaje(parte: int, total: int) -> str:
    return f"{100 * parte / total:.1f}".replace(".", ",") + " %"


def _miles(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def pares() -> list[tuple[str, str]]:
    """(tuit, titular del artículo) de cada tuit con texto del trozo grande."""
    tuits = {fila["id"]: fila["headline"] for fila in _leer(TITULARES)}
    articulos = {fila["id"]: fila["targetTitle"] for fila in _leer(CUERPOS)}
    if len(articulos) != TUITS:
        raise SystemExit(f"el fichero de cuerpos no tiene los {TUITS} tuits")
    if not set(articulos) <= set(tuits):
        raise SystemExit("hay cuerpos sin su tuit en el fichero de titulares")
    return [
        (tuits[identificador], titular) for identificador, titular in articulos.items()
    ]


def main() -> None:
    todos = pares()
    vacios = sum(1 for tuit, _ in todos if not tuit.strip())
    sin_titular = sum(1 for _, titular in todos if not titular.strip())
    tal_cual = sum(1 for tuit, titular in todos if tuit != titular)
    normalizados = sum(
        1 for tuit, titular in todos if _normalizar(tuit) != _normalizar(titular)
    )

    print(f"tuits del trozo grande con su artículo: {_miles(len(todos))}")
    print(
        f"  con el tuit vacío: {vacios} · con el titular del artículo vacío: {sin_titular}"
    )
    print(
        f"  difieren tal cual: {_miles(tal_cual)} ({_porcentaje(tal_cual, len(todos))})"
    )
    print(
        "  difieren sin contar mayúsculas ni espacios: "
        f"{_miles(normalizados)} ({_porcentaje(normalizados, len(todos))})"
    )


if __name__ == "__main__":
    main()
