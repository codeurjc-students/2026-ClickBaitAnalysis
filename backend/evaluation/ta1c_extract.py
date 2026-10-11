"""Extracto vendorizable de TA1C, el corpus de clickbait en español (issue #229).

TA1C («Te Ahorré Un Click», IberLEF 2025) son 3.500 tuits de 18 medios de 12
países hispanohablantes, cada uno etiquetado por tres personas (κ de Fleiss
0,825; manda la mayoría), con el artículo enlazado. Se distribuye como un
tarball de 6,4 MB (`TA1C_dataset_complete.tar.gz`, en
https://github.com/gmordecki/TA1C, rama `master`) con tres CSV, uno por parte
del reparto del propio corpus. Este módulo lo parte como el de Webis-17 (#121):

- **Teasers, etiquetas y reparto** → ``data/external/``, versionado. Es lo que
  consumen las señales que sólo miran el titular.
- **Artículos** (titular, subtítulo y cuerpo) → ``var/``, gitignorado y
  regenerable. Sólo hacen falta para la incoherencia, como en Webis-17.

QUÉ SE GUARDA, Y POR QUÉ

- ``headline`` es el **Teaser Text**: el titular, el texto del tuit o los dos,
  según el criterio del corpus, que es lo que leyó quien anotó. Es el texto
  CRUDO, no el «preprocesado» que el corpus sugiere (emojis y menciones
  sustituidos por palabras), porque producción recibe titulares crudos y la
  normalización es cosa de cada señal (``linear.rasgos`` ya quita menciones y
  enlaces).
- ``parte`` es el reparto del propio corpus (``train`` 2.100, ``validation`` 700,
  ``test`` 700), no uno nuevo: así las cifras se pueden comparar con las
  publicadas, que se midieron en su ``test``.
- ``anotaciones`` son las tres etiquetas individuales, como los
  ``truthJudgments`` de Webis-17: sin ellas no se puede medir el acuerdo.
- El titular del artículo va al fichero de cuerpos y **no** al de teasers, por
  lo mismo que en Webis-17: la anotación se hizo sobre el teaser.

    python -m backend.evaluation.ta1c_extract /tmp/ta1c/TA1C_dataset_complete.tar.gz
"""

import csv
import gzip
import io
import json
import sys
import tarfile
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]

DESTINO_TEASERS = _RAIZ / "data" / "external" / "ta1c.jsonl.gz"
DESTINO_CUERPOS = _RAIZ / "var" / "ta1c" / "ta1c_cuerpos.jsonl.gz"

PARTES = ("train", "validation", "test")
# Las dos únicas etiquetas del corpus; otra cosa es un fichero que no es éste.
ETIQUETAS = {"Clickbait": 1, "No": 0}


def _filas(tarball: tarfile.TarFile, parte: str) -> list[dict[str, str]]:
    """Las filas del CSV de una parte, leídas sin descomprimir a disco."""
    fichero = tarball.extractfile(f"TA1C_dataset_{parte}_complete.csv")
    if fichero is None:
        raise SystemExit(f"el tarball no trae el CSV de {parte}")
    texto = io.TextIOWrapper(fichero, encoding="utf-8", newline="")
    return list(csv.DictReader(texto))


def extraer(tarball_path: Path) -> dict[str, int]:
    """Escribe los dos ficheros y devuelve cuántas filas hay de cada parte."""
    # Hay cuerpos de artículo de más de 128 KB, el límite por defecto del módulo.
    csv.field_size_limit(10**8)
    DESTINO_TEASERS.parent.mkdir(parents=True, exist_ok=True)
    DESTINO_CUERPOS.parent.mkdir(parents=True, exist_ok=True)

    recuento = {}
    with (
        tarfile.open(tarball_path) as tarball,
        gzip.open(DESTINO_TEASERS, "wt", encoding="utf-8") as teasers,
        gzip.open(DESTINO_CUERPOS, "wt", encoding="utf-8") as cuerpos,
    ):
        for parte in PARTES:
            filas = _filas(tarball, parte)
            for fila in filas:
                etiquetas = [
                    fila["Tag Value"],
                    fila["First Annotator Tag"],
                    fila["Second Annotator Tag"],
                    fila["Third Annotator Tag"],
                ]
                desconocidas = set(etiquetas) - set(ETIQUETAS)
                if desconocidas:
                    raise SystemExit(
                        f"etiqueta desconocida {desconocidas} en el tuit {fila['Tweet ID']}"
                    )
                teasers.write(
                    json.dumps(
                        {
                            "id": fila["Tweet ID"],
                            "parte": parte,
                            "medio": fila["Media Name"],
                            "pais": fila["Media Origin"],
                            "headline": fila["Teaser Text"].strip(),
                            "label": ETIQUETAS[fila["Tag Value"]],
                            "anotaciones": [
                                ETIQUETAS[etiqueta] for etiqueta in etiquetas[1:]
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                cuerpos.write(
                    json.dumps(
                        {
                            "id": fila["Tweet ID"],
                            "titulo": fila["Article Title"],
                            "subtitulo": fila["Article Subtitle"],
                            "cuerpo": fila["Article Cleaned Text"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            recuento[parte] = len(filas)
    return recuento


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[-1].strip())
        raise SystemExit(1)

    origen = Path(sys.argv[1])
    if not origen.exists():
        print(f"no encuentro {origen}")
        print(
            "Descárgalo de https://github.com/gmordecki/TA1C "
            "(TA1C_dataset_complete.tar.gz, rama master)"
        )
        raise SystemExit(1)

    for parte, filas in extraer(origen).items():
        print(f"{parte}: {filas}")
    for destino in (DESTINO_TEASERS, DESTINO_CUERPOS):
        print(f"  {destino.stat().st_size / 1e6:8.2f} MB  {destino}")
