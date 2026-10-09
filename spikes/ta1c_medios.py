"""#229 (2026-10-08) - TA1C por dentro: cada parte, cada medio y los cuerpos.

Las cifras de TA1C que citan `data/external/ATTRIBUTION.md` y la sección de #229
del README: cuántos teasers y cuánto clickbait hay en cada parte del corpus, la
proporción de clickbait de cada medio —que es el riesgo de vocabulario de fuente
que hereda el lineal en español (#231)— y cuántos artículos llegan sin cuerpo.
Desde #232 (2026-10-09), también cuántos medios hay en cada parte: si están
los mismos en las tres, `test` no mide medios que el modelo no haya visto.

Lee el extracto versionado (`data/external/ta1c.jsonl.gz`) y los cuerpos de
`var/ta1c/`, que se regeneran con `python -m backend.evaluation.ta1c_extract`.

Ejecutar desde la raíz: .venv/bin/python spikes/ta1c_medios.py
"""

import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.evaluation.ta1c_extract import (  # noqa: E402
    DESTINO_CUERPOS,
    DESTINO_TEASERS,
)


def _leer(ruta: Path) -> list[dict]:
    with gzip.open(ruta, "rt", encoding="utf-8") as fichero:
        return [json.loads(linea) for linea in fichero]


def main() -> None:
    teasers = _leer(DESTINO_TEASERS)
    clickbait = sum(teaser["label"] for teaser in teasers)
    print(
        f"{len(teasers)} teasers · clickbait {clickbait} ({clickbait / len(teasers):.1%})"
    )
    for parte in ("train", "validation", "test"):
        etiquetas = [teaser["label"] for teaser in teasers if teaser["parte"] == parte]
        print(
            f"  {parte:10} {len(etiquetas):5} · clickbait {sum(etiquetas)} "
            f"({sum(etiquetas) / len(etiquetas):.1%})"
        )
    medios_por_parte = {
        parte: {teaser["medio"] for teaser in teasers if teaser["parte"] == parte}
        for parte in ("train", "validation", "test")
    }
    en_las_tres = set.intersection(*medios_por_parte.values())
    print(
        "  medios: "
        + ", ".join(
            f"{parte} {len(medios)}" for parte, medios in medios_por_parte.items()
        )
        + f"; en las tres partes, {len(en_las_tres)}"
    )

    por_medio: dict[tuple[str, str], list[int]] = defaultdict(list)
    for teaser in teasers:
        por_medio[(teaser["medio"], teaser["pais"])].append(teaser["label"])
    paises = {pais for _, pais in por_medio}
    print(
        f"\n{len(por_medio)} medios · {len(paises)} valores de país, "
        "de menos a más clickbait:"
    )
    for (medio, pais), etiquetas in sorted(
        por_medio.items(), key=lambda par: sum(par[1]) / len(par[1])
    ):
        print(
            f"  {medio:28} {pais:14} {len(etiquetas):4} teasers · "
            f"clickbait {sum(etiquetas) / len(etiquetas):.1%}"
        )

    cuerpos = _leer(DESTINO_CUERPOS)
    vacios = {articulo["id"] for articulo in cuerpos if not articulo["cuerpo"].strip()}
    print(f"\n{len(cuerpos)} artículos · {len(vacios)} sin cuerpo")
    for parte in ("train", "validation", "test"):
        de_la_parte = sum(
            1
            for teaser in teasers
            if teaser["parte"] == parte and teaser["id"] in vacios
        )
        print(f"  {parte:10} {de_la_parte} sin cuerpo")


if __name__ == "__main__":
    main()
