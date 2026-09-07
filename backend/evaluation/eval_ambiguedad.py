"""¿Contra qué techo estamos midiendo? (issue #121)

Todas las métricas del proyecto se han leído contra un 1,0 implícito: un F1 de
0,50 «es flojo» y uno de 0,90 «es bueno». Eso presupone que la tarea tiene una
respuesta correcta y que un sistema perfecto la acertaría siempre.

Webis-17 permite comprobarlo, porque guarda los **cinco juicios individuales** de
cada titular y no sólo su media. Con ellos se puede medir cuánto acierta una
persona contra el consenso de las demás — y eso es el techo realista.

QUÉ SE MIDE, Y POR QUÉ CADA COSA

1. **Unanimidad**: en qué fracción de titulares coinciden los cinco. Es la
   medida directa de cuánta zona gris tiene el problema.

2. **Techo humano**: F1 de un anotador contra el consenso. Ojo al sesgo: el
   consenso INCLUYE al anotador evaluado, así que el número sale, si acaso,
   generoso con el humano. Se deja así porque excluirlo cambia el tamaño del
   grupo entre titulares y complica la comparación más de lo que la mejora.

3. **Rendimiento por unanimidad**: separar los titulares donde los cinco están de
   acuerdo de aquellos donde no. Esto explica por qué un mismo modelo saca 0,95
   en Chakraborty y 0,63 en Webis — Chakraborty etiqueta POR FUENTE y ese método
   **no puede producir un caso dudoso**, así que mide sólo la mitad fácil.

4. **Reparto de errores**: si los fallos se concentran en la zona dudosa por
   encima de lo que le tocaría por tamaño, el sistema se equivoca donde también
   dudan las personas — que es muy distinto de equivocarse al azar.

5. **Confianza contra duda humana**: si el modelo baja su confianza justo donde
   los anotadores discrepan, esa confianza es información y merece llegar a la
   interfaz en vez de un sí/no (R3.8).

    NLP_BACKEND=local python -m backend.evaluation.eval_ambiguedad
"""

import json
from pathlib import Path

from sklearn.metrics import precision_recall_fscore_support

from backend.evaluation.eval_external import load_records
from backend.integrations.nlp import dedicated, lexical, linear

_RAIZ = Path(__file__).resolve().parents[2]
SPLIT = "validation170630"  # el único con truthJudgments vendorizados


def binariza(juicios: list[float]) -> list[int]:
    """Cada juicio individual, a 0/1 con el mismo corte que usa el corpus."""
    return [1 if j > 0.5 else 0 for j in juicios]


def es_unanime(registro: dict) -> bool:
    return len(set(binariza(registro["truthJudgments"]))) == 1


def techo_humano(registros: list[dict]) -> dict:
    """Cuánto acierta UNA persona contra el consenso de su grupo.

    Es el listón realista de la tarea: ningún sistema debería juzgarse contra un
    1,0 si las personas que generaron las etiquetas no llegan ahí.
    """
    unanimes = coincidencias = juicios_totales = 0
    uno, consenso_de_todos = [], []

    for r in registros:
        juicios = binariza(r["truthJudgments"])
        if not juicios:
            continue
        consenso = 1 if sum(juicios) * 2 > len(juicios) else 0
        unanimes += len(set(juicios)) == 1
        coincidencias += sum(j == consenso for j in juicios)
        juicios_totales += len(juicios)
        uno.append(juicios[0])
        consenso_de_todos.append(consenso)

    p, r_, f1, _ = precision_recall_fscore_support(
        consenso_de_todos, uno, average="binary", zero_division=0
    )
    return {
        "n": len(registros),
        "unanimidad": unanimes / len(registros),
        "coincidencia_individual": coincidencias / juicios_totales,
        "precision": p,
        "recall": r_,
        "f1": f1,
    }


def metricas(y: list[int], pred: list[int]) -> dict:
    p, r, f1, _ = precision_recall_fscore_support(
        y, pred, average="binary", zero_division=0
    )
    exacto = sum(a == b for a, b in zip(pred, y, strict=True)) / len(y)
    return {
        "n": len(y),
        "pos": sum(y) / len(y),
        "acierto": exacto,
        "precision": p,
        "recall": r,
        "f1": f1,
    }


def por_unanimidad(registros: list[dict], pred: list[int]) -> dict[str, dict]:
    """Rendimiento separando la zona limpia de la gris.

    El F1 no es comparable entre los dos grupos —el unánime está mucho más
    desbalanceado, y eso hunde la precisión de cualquier señal que se pase de
    marcar—, así que se devuelve también el RECALL, que sólo mira los positivos
    y por tanto no lo toca el balance.
    """
    grupos = {
        "todo": list(range(len(registros))),
        "unanimes": [i for i, r in enumerate(registros) if es_unanime(r)],
        "dudosos": [i for i, r in enumerate(registros) if not es_unanime(r)],
    }
    return {
        nombre: metricas([registros[i]["label"] for i in idx], [pred[i] for i in idx])
        for nombre, idx in grupos.items()
    }


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %"


def _cache_dedicada(registros: list[dict]) -> tuple[list[int], list[float]]:
    """Predicciones y confianza del modelo dedicado, cacheadas.

    Clasificar 19.484 titulares cuesta minutos y es determinista. La caché va en
    ``var/`` —derivado regenerable— y verifica los ids, no sólo el nombre del
    fichero: una caché de otra muestra daría un resultado equivocado en silencio.
    """
    cache = _RAIZ / "var" / f"dedicada_{SPLIT}.json"
    ids = [r["id"] for r in registros]
    if cache.exists():
        guardado = json.loads(cache.read_text(encoding="utf-8"))
        if guardado["ids"] == ids:
            print("  (reusando la caché de predicciones)")
            return guardado["pred"], guardado["score"]
        print("  (la caché no corresponde a este split: recalculando)")

    from transformers import pipeline

    print(f"  clasificando {len(ids)} con {dedicated.MODEL}...", flush=True)
    pipe = pipeline("text-classification", model=dedicated.MODEL)
    salida = pipe([r["headline"] for r in registros], batch_size=32)
    positiva = next(k for k, v in dedicated.ETIQUETAS.items() if v == "clickbait")
    pred = [int(s["label"] == positiva) for s in salida]
    score = [float(s["score"]) for s in salida]

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"ids": ids, "pred": pred, "score": score}), encoding="utf-8"
    )
    return pred, score


if __name__ == "__main__":
    registros = load_records(SPLIT)
    print(f"{SPLIT}: {len(registros)} titulares\n")

    # --- 1 y 2 · el techo ---
    t = techo_humano(registros)
    print("=" * 78)
    print("EL TECHO DE LA TAREA")
    print("=" * 78)
    print(f"  los 5 anotadores de acuerdo         {_pct(t['unanimidad']):>7}")
    print(
        f"  un juicio coincide con el consenso  {_pct(t['coincidencia_individual']):>7}"
    )
    print(
        f"\n  UN ANOTADOR contra el consenso:  F1 {t['f1']:.3f}  (P {t['precision']:.3f} · R {t['recall']:.3f})"
    )
    print("  -> ningún sistema debería juzgarse contra un 1,0")

    # --- 3 · las señales, separando la zona gris ---
    print(f"\n{'=' * 78}\nLAS SEÑALES SEGÚN CUÁNTO DUDARON LOS ANOTADORES\n{'=' * 78}")
    pred_dedicada, score = _cache_dedicada(registros)
    señales = {
        "lexical": [
            int(lexical.detect(r["headline"]).data["is_clickbait"]) for r in registros
        ],
        "linear": [
            int(linear.predict(r["headline"]).data["is_clickbait"]) for r in registros
        ],
        "dedicada": pred_dedicada,
    }

    print(
        f"\n  {'señal':10} {'grupo':10} {'n':>6} {'%pos':>6} {'prec':>7} {'RECALL':>8} {'F1':>7}"
    )
    for nombre, pred in señales.items():
        for grupo, m in por_unanimidad(registros, pred).items():
            print(
                f"  {nombre:10} {grupo:10} {m['n']:>6} {_pct(m['pos']):>6} "
                f"{m['precision']:7.3f} {m['recall']:8.3f} {m['f1']:7.3f}"
            )
        print()
    print("  El RECALL es la columna comparable entre grupos: no lo toca el balance.")

    # --- 4 · dónde caen los errores ---
    fallos = [i for i, p in enumerate(pred_dedicada) if p != registros[i]["label"]]
    en_dudosos = sum(1 for i in fallos if not es_unanime(registros[i]))
    proporcion_dudosos = sum(1 for r in registros if not es_unanime(r)) / len(registros)
    print(f"\n{'=' * 78}\nDÓNDE FALLA LA SEÑAL DEDICADA\n{'=' * 78}")
    print(
        f"  fallos en la zona dudosa   {_pct(en_dudosos / len(fallos))} de {len(fallos)}"
    )
    print(f"  la zona dudosa es          {_pct(proporcion_dudosos)} del corpus")
    print(
        "  -> si el primero supera claramente al segundo, falla donde dudan las personas"
    )

    # --- 5 · la confianza ---
    print(f"\n{'=' * 78}\n¿DUDA EL MODELO DONDE DUDAN LAS PERSONAS?\n{'=' * 78}")
    for nombre, cond in (("unánimes", True), ("dudosos", False)):
        idx = [i for i, r in enumerate(registros) if es_unanime(r) == cond]
        media = sum(score[i] for i in idx) / len(idx)
        bajos = sum(1 for i in idx if score[i] < 0.9) / len(idx)
        print(
            f"  {nombre:10} confianza media {media:.3f}   por debajo de 0,9: {_pct(bajos):>7}"
        )
    print("\n  Nadie se lo enseñó: se entrenó con la etiqueta binaria, nunca vio")
    print("  los juicios individuales. Argumento para exponer la confianza (R3.8).")
