"""Calibrar el umbral de incoherencia con método, no a ojo (issue #92).

``IncoherenceDetector.THRESHOLD = 0.3`` se puso **a estima**, sin contrastarlo con
nada. Y no es una señal cualquiera: es la única que mide *engaño*, la dimensión
que **manda sobre `forma`** en la jerarquía de ``_overall``, así que su umbral
decide el veredicto justo en los casos que más pesan.

EL PROBLEMA DEL 0,3 NO ES EL VALOR, ES QUE MEZCLA DOS PREGUNTAS

Un umbral confunde dos cosas que hay que medir por separado:

1. **¿Cuánta información tiene la señal?** Propiedad del detector, independiente
   de dónde se corte. Se mide con el AUC, que es exactamente la probabilidad de
   que un clickbait tenga menos similitud que un factual, sin cortar por ningún
   sitio. **Si sale ~0,5 la señal no vale y ningún umbral la salva.**

2. **¿Dónde conviene cortar?** Depende de qué cueste cada tipo de error, y eso es
   una decisión de producto, no de datos.

EL MÉTODO

- **Elegir en unos datos, reportar en otros.** Coger el corte que maximiza el F1
  y presentar ese F1 es hacer trampa: el número sale inflado porque el umbral se
  ajustó a esos mismos datos. Se calibra en una mitad y se mide en la otra, igual
  que #72 hizo con los splits.

- **Criterio declarado antes de mirar la curva.** Como `engano` pisa a `forma`,
  un falso positivo suyo declara «engañoso» por encima de las otras tres señales:
  su **precisión pesa más que su recall**. El criterio es «el mayor recall con
  precisión ≥ MIN_PRECISION», no el argmax de F1 — que se reporta igualmente para
  que la elección quede a la vista y no escondida.

- **Mirar la forma de la curva, no sólo su máximo.** Un óptimo en un pico estrecho
  es frágil aunque esté validado; uno en una meseta permite coger un valor redondo.

DOS LÍMITES QUE EL NÚMERO ARRASTRA, Y QUE VAN A LA FICHA

El modelo trunca a 256 tokens y los cuerpos de Webis miden 959 de media: el
**84 %** se corta. Lo que se calibra es «titular contra el primer cuarto del
artículo». Y se calibra sobre **tuits**, no titulares de portada.

Requiere los cuerpos extraídos en ``var/`` (ver ``webis_extract``):

    NLP_BACKEND=local python -m backend.evaluation.eval_incoherencia
"""

import gzip
import json
from pathlib import Path

from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)

from backend.evaluation.eval_external import load_records
from backend.integrations.nlp.incoherence import IncoherenceDetector

_RAIZ = Path(__file__).resolve().parents[2]
SPLIT = "validation170630"
CUERPOS = _RAIZ / "var" / "webis" / f"webis17_{SPLIT}_cuerpos.jsonl.gz"
CACHE = _RAIZ / "var" / f"similitudes_{SPLIT}.json"

SEMILLA = 24
MITAD_CALIBRACION = 0.5

# La precisión mínima exigible a una señal que PISA a las demás. Es una decisión
# de producto, no un resultado: se fija aquí, antes de ver ninguna curva, para
# que elegir el umbral no sea elegir también el criterio con el que juzgarlo.
MIN_PRECISION = 0.50


def cargar_pares() -> list[dict]:
    """Titulares con su cuerpo, etiqueta y truthMean."""
    if not CUERPOS.exists():
        raise SystemExit(
            f"faltan los cuerpos en {CUERPOS}\n"
            "Genéralos con: python -m backend.evaluation.webis_extract <zip>"
        )

    cuerpos = {}
    with gzip.open(CUERPOS, "rt", encoding="utf-8") as f:
        for linea in f:
            c = json.loads(linea)
            cuerpos[c["id"]] = " ".join(c["paragraphs"]).strip()

    pares = []
    for r in load_records(SPLIT):
        cuerpo = cuerpos.get(r["id"], "")
        if cuerpo:
            pares.append({**r, "content": cuerpo})
    return pares


def similitudes(pares: list[dict]) -> list[float]:
    """Similitud coseno titular↔cuerpo, cacheada.

    Se calcula con el MISMO modelo que usa la señal en producción, leído de su
    ficha: calibrar con otro daría un umbral que no vale para lo que se shipea.
    """
    ids = [p["id"] for p in pares]
    if CACHE.exists():
        guardado = json.loads(CACHE.read_text(encoding="utf-8"))
        if guardado["ids"] == ids:
            print("  (reusando las similitudes cacheadas)")
            return guardado["sim"]
        print("  (la caché no corresponde a estos pares: recalculando)")

    from sentence_transformers import SentenceTransformer

    modelo = SentenceTransformer(IncoherenceDetector.MODEL)
    print(
        f"  calculando {len(pares)} pares con {IncoherenceDetector.MODEL}...",
        flush=True,
    )
    emb_t = modelo.encode(
        [p["headline"] for p in pares], batch_size=64, show_progress_bar=False
    )
    emb_c = modelo.encode(
        [p["content"] for p in pares], batch_size=64, show_progress_bar=False
    )
    sim = [
        float(modelo.similarity(a, b).item()) for a, b in zip(emb_t, emb_c, strict=True)
    ]

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"ids": ids, "sim": sim}), encoding="utf-8")
    return sim


def barrido(y: list[int], sim: list[float], pasos: int = 101) -> list[dict]:
    """Precisión, recall y F1 para cada umbral posible.

    OJO AL SIGNO: la señal marca clickbait cuando la similitud está POR DEBAJO
    del umbral, al revés que un score normal. Equivocarlo invierte la curva y da
    un óptimo perfectamente creíble y perfectamente falso.
    """
    salida = []
    for i in range(pasos):
        umbral = i / (pasos - 1)
        pred = [1 if s < umbral else 0 for s in sim]
        p, r, f1, _ = precision_recall_fscore_support(
            y, pred, average="binary", zero_division=0
        )
        salida.append(
            {
                "umbral": umbral,
                "precision": p,
                "recall": r,
                "f1": f1,
                "marcados": sum(pred) / len(pred),
            }
        )
    return salida


def elegir(curva: list[dict], min_precision: float = MIN_PRECISION) -> dict | None:
    """El mayor recall que respeta el suelo de precisión.

    No es el argmax de F1: F1 trata por igual los dos errores, y aquí no lo son.
    Un falso positivo de esta señal declara «engañoso» pisando a las otras tres.
    """
    validos = [
        c for c in curva if c["precision"] >= min_precision and c["marcados"] > 0
    ]
    return max(validos, key=lambda c: c["recall"]) if validos else None


def meseta(
    curva: list[dict], elegido: dict, tolerancia: float = 0.01
) -> tuple[float, float]:
    """Rango de umbrales cuyo F1 queda a menos de `tolerancia` del elegido.

    Es la medida de si el óptimo es robusto o es un pico afortunado.
    """
    cerca = [c["umbral"] for c in curva if abs(c["f1"] - elegido["f1"]) <= tolerancia]
    return (min(cerca), max(cerca)) if cerca else (elegido["umbral"], elegido["umbral"])


def señales_de_forma(pares: list[dict]) -> list[int]:
    """¿Dice alguna señal de `forma` que esto es clickbait?

    Se combinan con un OR a propósito: aquí no interesa el veredicto de la
    dimensión sino si CUALQUIERA de las tres lo vio. Los casos que justifican la
    existencia de `engano` son aquellos donde NINGUNA lo vio y sin embargo
    engañaba — el titular sobrio cuyo cuerpo no cumple.
    """
    from backend.integrations.nlp import lexical, linear

    cache = _RAIZ / "var" / f"dedicada_{SPLIT}.json"
    dedicada = None
    if cache.exists():
        guardado = json.loads(cache.read_text(encoding="utf-8"))
        if guardado["ids"] == [p["id"] for p in pares]:
            dedicada = guardado["pred"]
    if dedicada is None:
        print("  (sin caché de la señal dedicada: se usan sólo léxico y lineal)")
        dedicada = [0] * len(pares)

    return [
        int(
            bool(lexical.detect(p["headline"]).data["is_clickbait"])
            or bool(linear.predict(p["headline"]).data["is_clickbait"])
            or bool(d)
        )
        for p, d in zip(pares, dedicada, strict=True)
    ]


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %"


if __name__ == "__main__":
    import random

    pares = cargar_pares()
    print(f"{len(pares)} pares titular↔cuerpo con etiqueta\n")
    sim = similitudes(pares)
    y = [p["label"] for p in pares]

    # ------------------------------------------------------ 1 · sin umbral
    print(
        f"\n{'=' * 78}\n1 · ¿CUÁNTA INFORMACIÓN TIENE LA SEÑAL?  (sin cortar por ningún lado)\n{'=' * 78}"
    )
    # Se niega la similitud porque la convención de sklearn es «score alto =
    # clase positiva», y aquí es al revés: menos similitud, más clickbait.
    score = [-s for s in sim]
    roc = roc_auc_score(y, score)
    pr = average_precision_score(y, score)
    print(f"  ROC-AUC          {roc:.3f}   (0,5 = moneda al aire)")
    print(
        f"  PR-AUC           {pr:.3f}   (línea base = {sum(y) / len(y):.3f}, la tasa de positivos)"
    )
    if roc < 0.6:
        print("  -> la señal apenas separa: el problema NO es el umbral")
    else:
        print("  -> hay señal; tiene sentido buscar dónde cortar")

    # ------------------------------- 2 y 3 · elegir aquí, reportar allá
    rnd = random.Random(SEMILLA)
    idx = list(range(len(pares)))
    rnd.shuffle(idx)
    corte = int(len(idx) * MITAD_CALIBRACION)
    cal, test = idx[:corte], idx[corte:]

    print(
        f"\n{'=' * 78}\n2 · UMBRAL ELEGIDO EN CALIBRACIÓN ({len(cal)}), MEDIDO EN TEST ({len(test)})\n{'=' * 78}"
    )
    curva_cal = barrido([y[i] for i in cal], [sim[i] for i in cal])

    elegido = elegir(curva_cal)
    mejor_f1 = max(curva_cal, key=lambda c: c["f1"])

    if elegido is None:
        print(f"  NINGÚN umbral alcanza precisión >= {MIN_PRECISION}")
        print(
            f"  el mejor F1 posible es {mejor_f1['f1']:.3f} con precisión {mejor_f1['precision']:.3f}"
        )
        print("  -> con este criterio la señal no debería votar")
        raise SystemExit(0)

    print(f"  criterio: mayor recall con precisión >= {MIN_PRECISION}")
    print(f"    umbral elegido        {elegido['umbral']:.2f}")
    print(
        f"    en calibración        P {elegido['precision']:.3f} · R {elegido['recall']:.3f} · F1 {elegido['f1']:.3f}"
    )
    print("\n  para comparar, el argmax de F1 habría dado:")
    print(f"    umbral                {mejor_f1['umbral']:.2f}")
    print(
        f"    en calibración        P {mejor_f1['precision']:.3f} · R {mejor_f1['recall']:.3f} · F1 {mejor_f1['f1']:.3f}"
    )

    y_test, sim_test = [y[i] for i in test], [sim[i] for i in test]
    print("\n  EN TEST (el número honesto, sobre datos que no eligieron el umbral):")
    for nombre, u in (
        ("umbral actual, a ojo", IncoherenceDetector.THRESHOLD),
        ("elegido por criterio", elegido["umbral"]),
        ("argmax de F1", mejor_f1["umbral"]),
    ):
        pred = [1 if s < u else 0 for s in sim_test]
        p, r, f1, _ = precision_recall_fscore_support(
            y_test, pred, average="binary", zero_division=0
        )
        print(
            f"    {nombre:24} u={u:.2f}  P {p:.3f} · R {r:.3f} · F1 {f1:.3f}  (marca {_pct(sum(pred) / len(pred))})"
        )

    # ------------------------------------------------- 4 · ¿es estable?
    bajo, alto = meseta(curva_cal, mejor_f1)
    print(f"\n{'=' * 78}\n4 · ¿ES ESTABLE EL ÓPTIMO?\n{'=' * 78}")
    print(f"  umbrales con F1 a menos de 0,01 del mejor: de {bajo:.2f} a {alto:.2f}")
    if alto - bajo >= 0.05:
        print(
            "  -> es una MESETA: el valor exacto da igual, se puede coger uno redondo"
        )
    else:
        print("  -> es un PICO estrecho: el óptimo es frágil y conviene desconfiar")

    print(f"\n  {'umbral':>7} {'marca':>7} {'prec':>7} {'recall':>7} {'F1':>7}")
    for c in curva_cal[::5]:
        if 0.15 <= c["umbral"] <= 0.85:
            print(
                f"  {c['umbral']:7.2f} {_pct(c['marcados']):>7} {c['precision']:7.3f} "
                f"{c['recall']:7.3f} {c['f1']:7.3f}"
            )

    # ---------------------------------------------------------------------
    # 5 · La pregunta que de verdad justifica la señal
    #
    # Todo lo anterior mide la incoherencia contra la etiqueta de CLICKBAIT, y
    # esta señal no existe para eso: existe para cazar el titular SOBRIO que
    # engaña, el caso que las señales de forma no pueden ver por construcción.
    #
    # Si en ese subconjunto no separa, el problema no es el umbral: es que la
    # señal no aporta donde se justifica su existencia, y entonces lo que hay
    # que revisar es su sitio en la jerarquía de `_overall`.
    # ---------------------------------------------------------------------
    print(
        f"\n{'=' * 78}\n5 · ¿APORTA DONDE LAS SEÑALES DE FORMA NO LLEGAN?\n{'=' * 78}"
    )
    forma = señales_de_forma(pares)
    sobrios = [i for i in range(len(pares)) if forma[i] == 0]
    enganosos = [i for i in sobrios if y[i] == 1]

    print(
        f"  titulares que NINGUNA señal de forma marca   {len(sobrios)} ({_pct(len(sobrios) / len(pares))})"
    )
    print(
        f"  de esos, los humanos dicen que SÍ engañaban   {len(enganosos)} ({_pct(len(enganosos) / len(sobrios))})"
    )
    print("  -> ése es exactamente el hueco que `engano` debería cubrir")

    y_sobrios = [y[i] for i in sobrios]
    sim_sobrios = [sim[i] for i in sobrios]
    if len(set(y_sobrios)) > 1:
        roc_sobrios = roc_auc_score(y_sobrios, [-s for s in sim_sobrios])
        print(f"\n  ROC-AUC de la incoherencia AHÍ   {roc_sobrios:.3f}")
        print(f"  (contra {roc:.3f} sobre el corpus entero)")
        if roc_sobrios < 0.6:
            print("  -> apenas separa donde más falta hace")
        else:
            print("  -> sí separa donde más falta hace: la dimensión se justifica")

        print(f"\n  {'umbral':>7} {'recupera':>9} {'prec':>7} {'recall':>7}")
        for u in (0.30, 0.40, 0.46, 0.56):
            pred = [1 if s < u else 0 for s in sim_sobrios]
            p, r, _, _ = precision_recall_fscore_support(
                y_sobrios, pred, average="binary", zero_division=0
            )
            recuperados = sum(
                1 for k, s in enumerate(sim_sobrios) if s < u and y_sobrios[k] == 1
            )
            print(f"  {u:7.2f} {recuperados:>9} {p:7.3f} {r:7.3f}")
        print("\n  «recupera» = clickbait que NINGUNA otra señal habría detectado.")

    # ---------------------------------------------------------------------
    # 6 · ¿Arregla una cascada el problema de la tasa base?
    #
    # La precisión no es propiedad de la señal: es de la señal × la tasa base.
    # Con un 5,3 % de positivos esta señal no puede ser precisa aunque ordene
    # bien. Si otra filtra antes y sube esa tasa, la MISMA señal —mismo umbral,
    # mismo modelo— sería más precisa sin haber mejorado en nada.
    #
    # Eso es comprobable, y decide si encadenar señales compra algo. Ojo al
    # coste que no sale en estos números: una cascada NO es un contraste. Si B
    # sólo ve lo que A dejó pasar, B ya no puede discrepar de A en lo que A
    # descartó, y `AMBIGUO` deja de significar «dos señales miraron y no
    # coincidieron».
    # ---------------------------------------------------------------------
    print(f"\n{'=' * 78}\n6 · ¿COMPRA ALGO UNA CASCADA?\n{'=' * 78}")
    inc = [1 if s < IncoherenceDetector.THRESHOLD else 0 for s in sim]
    from backend.integrations.nlp import lexical, linear

    otras = {
        "lexical": [
            int(lexical.detect(p["headline"]).data["is_clickbait"]) for p in pares
        ],
        "linear": [
            int(linear.predict(p["headline"]).data["is_clickbait"]) for p in pares
        ],
    }
    cache_ded = _RAIZ / "var" / f"dedicada_{SPLIT}.json"
    if cache_ded.exists():
        guardado = json.loads(cache_ded.read_text(encoding="utf-8"))
        if guardado["ids"] == [p["id"] for p in pares]:
            otras["dedicada"] = guardado["pred"]

    print(
        f"\n  {'filtro previo':14} {'n dentro':>9} {'tasa base':>10} {'precisión de la incoherencia':>30}"
    )
    for nombre, pred in otras.items():
        dentro = [i for i in range(len(pares)) if pred[i] == 1]
        y_d = [y[i] for i in dentro]
        if len(set(y_d)) < 2:
            continue
        p_d = [inc[i] for i in dentro]
        p, _, _, _ = precision_recall_fscore_support(
            y_d, p_d, average="binary", zero_division=0
        )
        print(
            f"  {nombre:14} {len(dentro):>9} {_pct(sum(y_d) / len(y_d)):>10} {p:>30.3f}"
        )
    p_sola, _, _, _ = precision_recall_fscore_support(
        y, inc, average="binary", zero_division=0
    )
    print(
        f"  {'(sin filtro)':14} {len(y):>9} {_pct(sum(y) / len(y)):>10} {p_sola:>30.3f}"
    )

    print(f"\n  {'combinación':30} {'marca':>7} {'prec':>7} {'recall':>7} {'F1':>7}")
    for nombre, pred in otras.items():
        for etiqueta, combinado in (
            (f"{nombre} solo", pred),
            (
                f"{nombre} ∧ incoherencia",
                [a & b for a, b in zip(pred, inc, strict=True)],
            ),
            (
                f"{nombre} ∨ incoherencia",
                [a | b for a, b in zip(pred, inc, strict=True)],
            ),
        ):
            p, r, f1, _ = precision_recall_fscore_support(
                y, combinado, average="binary", zero_division=0
            )
            print(
                f"  {etiqueta:30} {_pct(sum(combinado) / len(y)):>7} "
                f"{p:7.3f} {r:7.3f} {f1:7.3f}"
            )
        print()
    print("  Si ninguna combinación bate a la señal sola, la cascada no compra")
    print("  veredicto — aunque sí suba la precisión de la incoherencia dentro.")
