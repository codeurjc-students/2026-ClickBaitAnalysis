"""Extracto vendorizable del Webis-Clickbait-17 completo (issue #121).

El corpus se distribuye como un zip de **937 MB** que no entra en el repositorio:
la mayor parte son imágenes de los tuits, que no usamos. Este módulo saca de ahí
lo que sí sirve y lo parte en dos por una razón de tamaño:

- **Titulares** (1,1 MB) → ``data/external/``, versionado. Es lo que consumen las
  cuatro señales de ``forma``.
- **Cuerpos de artículo** (29 MB) → ``var/``, gitignorado y regenerable. Sólo
  hacen falta para calibrar el umbral de ``engano``, y 29 MB en git no se
  justifican por eso.

QUÉ SE GUARDA, Y POR QUÉ CADA COSA

- ``id`` — el extracto anterior (#76) no lo guardaba, así que comparar los dos
  splits obligó a cruzarlos por texto normalizado. Con el id los cruces son
  exactos.
- ``truthJudgments`` — los CINCO juicios individuales, no sólo su media. Es lo
  que permite medir el acuerdo entre anotadores y, con él, el techo de la tarea
  (ver ``eval_ambiguedad``). Sin esto, un F1 de 0,63 no se puede interpretar.
- ``targetTitle`` va al fichero de cuerpos y **no** al de titulares, a propósito:
  es el titular del artículo, distinto del tuit el 75 % de las veces, y la
  anotación humana se hizo sobre el TUIT. Usarlo con esa etiqueta sería etiquetar
  mal, y tenerlo lejos del fichero que consumen las señales evita la tentación.

Se descartan las instancias con ``postText`` vacío (54 de 19.538): un titular
vacío no es un caso difícil, es un caso inexistente, y contarlo como fallo de las
señales falsearía sus métricas a la baja.

    python -m backend.evaluation.webis_extract var/webis/clickbait17-train-170630.zip
"""

import gzip
import json
import sys
import zipfile
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]

DESTINO_TITULARES = _RAIZ / "data" / "external" / "webis17_validation170630.jsonl.gz"
DESTINO_CUERPOS = _RAIZ / "var" / "webis" / "webis17_validation170630_cuerpos.jsonl.gz"

# El zip se llama «train-170630» pero la carpeta de dentro dice «validation»: es
# la nomenclatura del Clickbait Challenge, donde el 170331 es el split de
# entrenamiento y éste el de validación. Son DISJUNTOS (medido: 1 titular en
# común de 2.380), así que no es una versión mayor del que ya teníamos, es el
# otro trozo. Confundirlos llevaría a evaluar un modelo sobre su entrenamiento.
CARPETA = "clickbait17-validation-170630"


def extraer(zip_path: Path) -> dict:
    """Escribe los dos ficheros y devuelve el recuento."""
    z = zipfile.ZipFile(zip_path)

    with z.open(f"{CARPETA}/truth.jsonl") as f:
        verdad = {}
        for linea in f:
            registro = json.loads(linea)
            verdad[registro["id"]] = registro

    DESTINO_TITULARES.parent.mkdir(parents=True, exist_ok=True)
    DESTINO_CUERPOS.parent.mkdir(parents=True, exist_ok=True)

    escritos = vacios = sin_etiqueta = 0
    with (
        z.open(f"{CARPETA}/instances.jsonl") as f,
        gzip.open(DESTINO_TITULARES, "wt", encoding="utf-8") as ft,
        gzip.open(DESTINO_CUERPOS, "wt", encoding="utf-8") as fc,
    ):
        for linea in f:
            registro = json.loads(linea)
            etiqueta = verdad.get(registro["id"])
            if etiqueta is None:
                sin_etiqueta += 1
                continue

            headline = " ".join(registro["postText"]).strip()
            if not headline:
                vacios += 1
                continue

            ft.write(
                json.dumps(
                    {
                        "id": registro["id"],
                        "headline": headline,
                        "label": 1 if etiqueta["truthClass"] == "clickbait" else 0,
                        "truthMean": etiqueta["truthMean"],
                        "truthJudgments": etiqueta["truthJudgments"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            fc.write(
                json.dumps(
                    {
                        "id": registro["id"],
                        "targetTitle": registro.get("targetTitle", ""),
                        "paragraphs": registro.get("targetParagraphs", []),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            escritos += 1

    return {"escritos": escritos, "vacios": vacios, "sin_etiqueta": sin_etiqueta}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[-1].strip())
        raise SystemExit(1)

    origen = Path(sys.argv[1])
    if not origen.exists():
        print(f"no encuentro {origen}")
        print("Descárgalo de https://zenodo.org/records/5530410 (CC BY 4.0)")
        raise SystemExit(1)

    resultado = extraer(origen)
    print(f"{resultado['escritos']} instancias escritas")
    if resultado["vacios"]:
        print(f"  {resultado['vacios']} descartadas por tener postText vacío")
    if resultado["sin_etiqueta"]:
        print(f"  {resultado['sin_etiqueta']} descartadas por no tener etiqueta")
    for destino in (DESTINO_TITULARES, DESTINO_CUERPOS):
        print(f"  {destino.stat().st_size / 1e6:8.2f} MB  {destino}")
