"""Split físico train/dev/test (issue #72).

Persiste la partición 60/20/20 del dataset Chakraborty en ficheros JSONL
(data/splits/), de forma que TODOS los consumidores (reglas, lineal, futuros
modelos) usen exactamente las mismas muestras aunque cada uno featurice a su
manera. Se persisten los pares CRUDOS (headline, label): los datos son el
contrato; los vectores son derivados y se recomputan aguas abajo.

- test: se corta PRIMERO y queda congelado (solo para el número final).
- dev: banco de pruebas del desarrollo (afinar umbrales, comparar modelos).
- train: entrenamiento.

Crear (una vez):  python -m backend.evaluation.splits
Cargar:           from backend.evaluation.splits import load_split

WEBIS-17, DESDE #78

`validation170630` (19.484) se parte en `webis_dev` (20 %) y `webis_test` (80 %),
estratificado y con la misma semilla. El lineal se entrena con `train170331`, la
otra parte de Webis, y elige y se mide con éstas: así el corpus de las
evaluaciones grandes (#92, #121, #124) no entrena ningún modelo. Se guardan los
`id` además del titular, para poder cruzarlos con los cuerpos de `var/`.

Crear (una vez):  python -m backend.evaluation.splits webis
"""

import json
from pathlib import Path

from sklearn.model_selection import train_test_split

from backend.evaluation.eval_lexical import load_dataset

SPLITS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "splits"

SEED = 24  # Misma semilla
TEST_SIZE = 0.2  # 20% del total, congelado.
DEV_SIZE = 0.25  # 0.25 * 0.8 = 20% del total.

NAMES = ("train", "dev", "test")

# Webis-17 (#78): la parte grande, partida para elegir y para probar.
WEBIS_ORIGEN = "validation170630"
WEBIS_DEV_SIZE = 0.2
WEBIS_NAMES = ("webis_dev", "webis_test")


def _path(name: str) -> Path:
    return SPLITS_DIR / f"{name}.jsonl"


def create_splits(force: bool = False) -> None:
    """Crea y persiste los tres splits. Falla si ya existen (salvo force=True):
    regenerarlos cambiaría QUÉ muestras ve cada modelo y rompería la
    comparabilidad de todos los resultados anteriores."""
    existing = [p.name for p in map(_path, NAMES) if p.exists()]
    if existing and not force:
        raise FileExistsError(
            f"Ya existen splits en {SPLITS_DIR} ({', '.join(existing)}). "
            "Regenerarlos invalida los resultados previos; usa force=True solo a sabiendas."
        )

    headlines, labels = zip(*load_dataset(), strict=True)

    # 1) Se congela el test (nunca se re-baraja).
    h_rest, h_test, y_rest, y_test = train_test_split(
        headlines, labels, test_size=TEST_SIZE, stratify=labels, random_state=SEED
    )
    # 2) El resto (80%) se parte en train/dev.
    h_train, h_dev, y_train, y_dev = train_test_split(
        h_rest, y_rest, test_size=DEV_SIZE, stratify=y_rest, random_state=SEED
    )

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    for name, (hs, ys) in {
        "train": (h_train, y_train),
        "dev": (h_dev, y_dev),
        "test": (h_test, y_test),
    }.items():
        with open(_path(name), "w", encoding="utf-8") as f:
            for headline, label in zip(hs, ys, strict=True):
                f.write(
                    json.dumps(
                        {"headline": headline, "label": label}, ensure_ascii=False
                    )
                    + "\n"
                )


def create_webis_splits(force: bool = False) -> None:
    """Parte `validation170630` en `webis_dev` y `webis_test` (#78).

    Falla si ya existen, por lo mismo que `create_splits`: regenerarlos
    cambiaría qué titulares eligen el modelo y cuáles lo miden.
    """
    from backend.evaluation.eval_external import load_records

    existing = [p.name for p in map(_path, WEBIS_NAMES) if p.exists()]
    if existing and not force:
        raise FileExistsError(
            f"Ya existen splits de Webis en {SPLITS_DIR} ({', '.join(existing)})."
        )

    registros = load_records(WEBIS_ORIGEN)
    etiquetas = [registro["label"] for registro in registros]
    dev, test = train_test_split(
        registros,
        test_size=1 - WEBIS_DEV_SIZE,
        stratify=etiquetas,
        random_state=SEED,
    )

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    for name, parte in zip(WEBIS_NAMES, (dev, test), strict=True):
        with open(_path(name), "w", encoding="utf-8") as f:
            for registro in parte:
                fila = {
                    "id": registro["id"],
                    "headline": registro["headline"],
                    "label": registro["label"],
                }
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def load_split(name: str) -> list[tuple[str, int]]:
    """Carga un split persistido → lista de (headline, label)."""
    if name not in NAMES + WEBIS_NAMES:
        raise ValueError(
            f"Split desconocido: {name!r} (usa uno de {NAMES + WEBIS_NAMES})"
        )
    path = _path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Genera los splits con: python -m backend.evaluation.splits"
        )
    with open(path, encoding="utf-8") as f:
        return [(record["headline"], record["label"]) for record in map(json.loads, f)]


if __name__ == "__main__":
    import sys

    if "webis" in sys.argv:
        create_webis_splits()
        nombres = WEBIS_NAMES
    else:
        create_splits()
        nombres = NAMES
    for name in nombres:
        print(f"{name}: {len(load_split(name))} titulares -> {_path(name)}")
