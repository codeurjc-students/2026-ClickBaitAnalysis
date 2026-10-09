"""¿Vale la incoherencia en español, y con qué umbral? (issue #233)

La incoherencia inglesa (`all-MiniLM-L6-v2`, umbral 0,3) se calibró en #92 con
`eval_incoherencia.py`: primero el AUC, que dice si la señal separa algo sin
cortar por ningún sitio, y después el umbral, elegido en una mitad y medido en
la otra. Éste hace lo mismo en español con un modelo multilingüe, y aplica la
regla publicada en la issue antes de medir.

LOS DATOS: TA1C `train` Y `validation`, Y `test` CERRADO

La incoherencia no se entrena, así que no hace falta reservar datos para
entrenar: se usan los pares titular–cuerpo de `train` y `validation` (sin los
de cuerpo vacío). `test` no se abre: lleva tres aperturas (#231, #232, #242).
La etiqueta es la de clickbait de TA1C, no una de engaño, como en #92.

LA REGLA (comentario en #233)

- (a) AUC ≥ `AUC_MINIMO` en todos los pares; y
- (b) en la mitad de elección hay algún umbral con precisión ≥ 0,50, y se elige
  el de mayor recall entre ellos (el criterio de #92, `elegir`).

Si se cumplen las dos, la incoherencia analiza el español con ese umbral. Si
no, no lo analiza, con un motivo medido.

Se mide por el camino de producción: `IncoherenceDetector` con el modelo, y el
cuerpo recortado con `_lead`. Las similitudes se guardan en `var/`, así que
volver a lanzarlo no vuelve a calcular nada.

    NLP_BACKEND=local .venv/bin/python -m backend.evaluation.eval_incoherencia_es
"""

import json
import random
from datetime import datetime
from pathlib import Path

from huggingface_hub import try_to_load_from_cache
from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)

from backend.evaluation.eval_incoherencia import (
    MIN_PRECISION,
    MITAD_CALIBRACION,
    SEMILLA,
    barrido,
    elegir,
    meseta,
)
from backend.evaluation.eval_ta1c import cargar
from backend.integrations.nlp.incoherence import IncoherenceDetector

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# La de `main` el 9 oct. Producción no fija revisiones (eso es de F, #234):
# el guion avisa si la descargada es otra.
REVISION = "e8f8c211226b"
PARTES = ("train", "validation")
AUC_MINIMO = 0.60  # (a) de la regla
CACHE = Path(__file__).resolve().parents[2] / "var" / "incoherencia_es"


def pares() -> list[dict]:
    """Los tuits de `train` y `validation` con cuerpo, con su etiqueta."""
    return [
        fila for parte in PARTES for fila in cargar(parte) if fila["cuerpo"].strip()
    ]


def _revision() -> str | None:
    """La revisión descargada: la carpeta de la caché lleva su commit."""
    ruta = try_to_load_from_cache(MODELO, "config.json")
    return Path(ruta).parent.name[:12] if isinstance(ruta, str) else None


def similitudes(filas: list[dict]) -> dict:
    """La similitud de cada par como en producción, guardada en `CACHE`."""
    ruta = CACHE / "similitudes.json"
    ids = [fila["id"] for fila in filas]
    if ruta.exists():
        guardado = json.loads(ruta.read_text(encoding="utf-8"))
        if guardado["ids"] == ids and guardado["modelo"] == MODELO:
            print(f"  (las similitudes guardadas el {guardado['fecha']})")
            return guardado

    detector = IncoherenceDetector(MODELO)
    modelo = detector._get_model()
    titulares = [fila["headline"] for fila in filas]
    cuerpos = [IncoherenceDetector._lead(fila["cuerpo"]) for fila in filas]
    print(f"  calculando {len(filas)} pares con {MODELO}…", flush=True)
    de_titulares = modelo.encode(titulares, batch_size=64, show_progress_bar=False)
    de_cuerpos = modelo.encode(cuerpos, batch_size=64, show_progress_bar=False)
    # Cuántos cuerpos, ya recortados, superan lo que el modelo lee: el resto se
    # pierde en silencio, y va a su ficha.
    cortados = sum(
        1
        for cuerpo in cuerpos
        if len(modelo.tokenizer(cuerpo)["input_ids"]) > modelo.max_seq_length
    )
    guardado = {
        "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
        "modelo": MODELO,
        "revision": _revision(),
        "max_tokens": modelo.max_seq_length,
        "cortados": cortados,
        "ids": ids,
        "sim": [
            float(modelo.similarity(titular, cuerpo).item())
            for titular, cuerpo in zip(de_titulares, de_cuerpos, strict=True)
        ],
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(guardado), encoding="utf-8")
    return guardado


def _medida(etiquetas: list[int], sim: list[float], umbral: float) -> str:
    votos = [int(similitud < umbral) for similitud in sim]
    precision, recall, f1, _ = precision_recall_fscore_support(
        etiquetas, votos, average="binary", zero_division=0
    )
    return (
        f"u={umbral:.2f} · P {precision:.3f} · R {recall:.3f} · F1 {f1:.3f} · "
        f"marca el {sum(votos) / len(votos):.1%}"
    )


def main() -> None:
    filas = pares()
    medido = similitudes(filas)
    sim = medido["sim"]
    etiquetas = [fila["label"] for fila in filas]
    if medido["revision"] != REVISION:
        print(
            f"  ⚠️ la revisión descargada es {medido['revision']}, no la {REVISION} de la regla"
        )
    print(
        f"\n== TA1C {' + '.join(PARTES)}: {len(filas)} pares con cuerpo, "
        f"{sum(etiquetas) / len(etiquetas):.1%} clickbait"
    )
    print(
        f"  {MODELO} ({medido['revision']}), {medido['max_tokens']} tokens: "
        f"{medido['cortados']} cuerpos ({medido['cortados'] / len(filas):.1%}) se cortan aún recortados"
    )

    # Menos similitud, más clickbait: se niega para la convención de sklearn.
    puntuacion = [-similitud for similitud in sim]
    auc = roc_auc_score(etiquetas, puntuacion)
    print("\n== 1 · ¿separa algo, sin cortar por ningún sitio?")
    print(
        f"  ROC-AUC {auc:.3f} · PR-AUC {average_precision_score(etiquetas, puntuacion):.3f} "
        f"(la base, {sum(etiquetas) / len(etiquetas):.3f})"
    )
    cumple_a = auc >= AUC_MINIMO
    print(
        f"  => (a) {'CUMPLE' if cumple_a else 'NO cumple'}: AUC {auc:.3f} frente a {AUC_MINIMO}"
    )

    indices = list(range(len(filas)))
    random.Random(SEMILLA).shuffle(indices)
    corte = int(len(indices) * MITAD_CALIBRACION)
    eleccion, comprobacion = indices[:corte], indices[corte:]
    curva = barrido([etiquetas[i] for i in eleccion], [sim[i] for i in eleccion])
    elegido = elegir(curva)
    mejor_f1 = max(curva, key=lambda punto: punto["f1"])
    print(
        f"\n== 2 · el umbral, elegido en una mitad ({len(eleccion)}) y medido en la otra ({len(comprobacion)})"
    )
    cumple_b = elegido is not None
    if elegido is None:
        print(
            f"  NINGÚN umbral llega a precisión {MIN_PRECISION} en la mitad de elección "
            f"(el mejor F1, {mejor_f1['f1']:.3f}, con P {mejor_f1['precision']:.3f})"
        )
    else:
        print(
            f"  elegido (mayor recall con P ≥ {MIN_PRECISION}): u={elegido['umbral']:.2f} · "
            f"P {elegido['precision']:.3f} · R {elegido['recall']:.3f} en la elección"
        )
    print(f"  => (b) {'CUMPLE' if cumple_b else 'NO cumple'}")

    etiquetas_c = [etiquetas[i] for i in comprobacion]
    sim_c = [sim[i] for i in comprobacion]
    print("\n  en la mitad que no eligió:")
    referencias = [("el del inglés (#92)", IncoherenceDetector.THRESHOLD)]
    if elegido is not None:
        referencias.insert(0, ("el elegido", elegido["umbral"]))
    referencias.append(("el argmax de F1", mejor_f1["umbral"]))
    for nombre, umbral in referencias:
        print(f"    {nombre:22} {_medida(etiquetas_c, sim_c, umbral)}")

    bajo, alto = meseta(curva, mejor_f1)
    print(
        f"\n  F1 a menos de 0,01 del mejor, de {bajo:.2f} a {alto:.2f}: "
        f"{'una meseta' if alto - bajo >= 0.05 else 'un pico estrecho'}"
    )
    print(f"\n  {'umbral':>7} {'marca':>7} {'P':>7} {'R':>7} {'F1':>7}")
    for punto in curva[::5]:
        if 0.15 <= punto["umbral"] <= 0.85:
            print(
                f"  {punto['umbral']:7.2f} {punto['marcados']:7.1%} {punto['precision']:7.3f} "
                f"{punto['recall']:7.3f} {punto['f1']:7.3f}"
            )

    aplica = cumple_a and cumple_b
    print(f"\n== {'APLICA en español' if aplica else 'NO aplica en español'}")
    (CACHE / "resultado.json").write_text(
        json.dumps(
            {
                "modelo": MODELO,
                "revision": medido["revision"],
                "pares": len(filas),
                "auc": auc,
                "umbral": elegido["umbral"] if elegido is not None else None,
                "aplica": aplica,
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
