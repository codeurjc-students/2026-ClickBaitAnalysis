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


def load_split(name: str) -> list[tuple[str, int]]:
    """Carga un split persistido → lista de (headline, label)."""
    if name not in NAMES:
        raise ValueError(f"Split desconocido: {name!r} (usa uno de {NAMES})")
    path = _path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Genera los splits con: python -m backend.evaluation.splits"
        )
    with open(path, encoding="utf-8") as f:
        return [(record["headline"], record["label"]) for record in map(json.loads, f)]


if __name__ == "__main__":
    create_splits()
    for name in NAMES:
        print(f"{name}: {len(load_split(name))} titulares -> {_path(name)}")
