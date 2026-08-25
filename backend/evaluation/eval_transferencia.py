"""¿Qué señal sobrevive fuera de su dominio? (issues #109, #115)

``eval_external`` (#76) midió la caída del léxico y el lineal en Webis-17. Faltaban
las otras dos piezas de la dimensión ``forma``, y ambas responden a una pregunta
que #109 dejó abierta:

**El zero-shot.** Es la única señal del sistema que nunca vio un corpus de
clickbait, así que es estructuralmente inmune al sesgo de fuente. Dentro de
dominio rinde flojo (63,7 % en dev), y cabía la hipótesis de que esa flojera
fuese en realidad la robustez de no haberse sobreajustado a nada: si aguantara
fuera mientras las demás se hunden, quitarle el voto sería el error contrario.

**Un modelo dedicado de terceros.** E3-02 dejó anotado sustituir el zero-shot
genérico por uno entrenado en clickbait «si llega la infra». Llegó. Pero un
modelo entrenado sobre Chakraborty hereda sus etiquetas por-fuente, y eso no lo
arregla tener más capacidad — la palanca es la supervisión, no el algoritmo. Su
puntuación DENTRO de Chakraborty no puede distinguir las dos cosas; sólo la
puntuación fuera lo hace.

De ahí el segundo bloque: **recall estratificado por ``truthMean``**, el juicio
medio de los anotadores de Webis. Un modelo que aprendió el concepto debería
detectar mejor el clickbait que los humanos marcaron como más flagrante. Uno que
memorizó un corpus, no: fallará parejo en toda la escala, o cerca.

Ese doble criterio —puntuación externa y respuesta a la intensidad— es el banco
de pruebas para cualquier candidato futuro (#115), con
``elozano/bert-base-cased-clickbait-news`` como caso de calibración conocido.

Correr con el backend LOCAL: en remoto los veredictos dependen de qué sirva
HuggingFace ese día, y entonces las cifras dejan de ser reproducibles.

    NLP_BACKEND=local python -m backend.evaluation.eval_transferencia
    NLP_BACKEND=local python -m backend.evaluation.eval_transferencia --muestra 600
"""

import asyncio
import json
import sys
from pathlib import Path

from sklearn.metrics import precision_recall_fscore_support

from backend.evaluation.eval_external import load_external
from backend.integrations.nlp import lexical, linear

_RAIZ = Path(__file__).resolve().parents[2]

# Modelo dedicado que E3-02 dejó anotado como mejora. Se conserva aquí como caso
# de calibración: su 99,7 % en Chakraborty dev frente a su F1 en Webis es el
# patrón que delata memorización, y sirve de referencia para juzgar candidatos.
DEDICADO = "elozano/bert-base-cased-clickbait-news"

MUESTRA_POR_DEFECTO = 600  # BART tarda ~1 s por titular; los 2459 serían 40 min


def muestra_estratificada(
    datos: list[tuple[str, int, float]], n: int, semilla: int = 24
):
    """Submuestra de Webis conservando su proporción real de clases.

    Se estratifica y no se corta por lo bruto porque Webis está desbalanceado
    (31 % positivos): una muestra aleatoria podría cambiar la tasa base, y con
    ella el listón contra el que se juzga el acierto.
    """
    import random

    rnd = random.Random(semilla)
    por_clase: dict[int, list] = {}
    for d in datos:
        por_clase.setdefault(d[1], []).append(d)

    muestra = []
    for items in por_clase.values():
        muestra.extend(rnd.sample(items, round(n * len(items) / len(datos))))
    rnd.shuffle(muestra)
    return muestra


def metricas(y: list[int], pred: list[int]) -> dict:
    """Acierto, precisión, recall y F1.

    El acierto se incluye para poder DESCARTARLO en voz alta: con Webis al 69 %
    de negativos, responder «no» a todo ya da 69 %, así que tres señales pueden
    parecer equivalentes en esa columna y separarse de 0,52 a 0,16 en F1.
    """
    p, r, f1, _ = precision_recall_fscore_support(
        y, pred, average="binary", zero_division=0
    )
    exacto = sum(a == b for a, b in zip(pred, y, strict=True)) / len(y)
    return {"acierto": exacto, "precision": p, "recall": r, "f1": f1}


def clase_mayoritaria(y: list[int]) -> float:
    """El listón: lo que acierta quien no mira el titular."""
    return max(sum(y), len(y) - sum(y)) / len(y)


def baratas(headlines: list[str]) -> dict[str, list[int]]:
    """Las dos señales que no cargan modelos: regex y un producto escalar."""
    return {
        "lexical": [int(lexical.detect(h).data["is_clickbait"]) for h in headlines],
        "linear": [int(linear.predict(h).data["is_clickbait"]) for h in headlines],
    }


def dedicado(headlines: list[str], modelo: str = DEDICADO) -> list[int]:
    """Clasifica con un modelo de la Hub entrenado EN clickbait.

    Las etiquetas no están normalizadas entre modelos (unos usan
    ``Clickbait``/``Normal``, otros ``LABEL_0``/``LABEL_1``), así que el mapeo se
    fija con una sonda de dos titulares inequívocos en vez de cablearlo: uno de
    manual y otro sobrio. Cablearlo al revés invertiría el resultado sin que
    ninguna excepción avisara.
    """
    from transformers import pipeline

    pipe = pipeline("text-classification", model=modelo)
    sonda = pipe(
        [
            "17 Things Nobody Tells You About Working From Home",
            "Federal Reserve raises interest rates by 0.25 percent",
        ]
    )
    positiva = sonda[0]["label"]
    if sonda[0]["label"] == sonda[1]["label"]:
        raise RuntimeError(
            f"{modelo}: la sonda no separa los dos casos ({sonda}); revisa el mapeo"
        )
    print(f"    etiqueta positiva de {modelo}: «{positiva}»")
    return [int(s["label"] == positiva) for s in pipe(headlines)]


def zero_shot_cacheado(headlines: list[str], etiqueta: str) -> list[int]:
    """Zero-shot con caché en disco, mismo criterio que ``eval_acoplamiento``.

    La clave lleva la etiqueta de la muestra (corpus, tamaño y semilla) porque es
    lo que determina QUÉ titulares entran: reutilizar la caché con otra muestra
    daría un resultado silenciosamente equivocado. Por eso además se comparan los
    titulares guardados, no sólo el nombre del fichero.
    """
    cache = _RAIZ / "var" / f"zero_shot_{etiqueta}.json"
    if cache.exists():
        guardado = json.loads(cache.read_text(encoding="utf-8"))
        if guardado["headlines"] == headlines:
            print(f"    (reusando {cache.name})")
            return guardado["veredictos"]
        print("    (la caché no corresponde a esta muestra: recalculando)")

    from backend.config.settings import settings
    from backend.integrations.nlp.factory import get_nlp_backend

    # El backend se anuncia porque cambia la naturaleza del resultado: en remoto
    # los números dependen de qué sirva HuggingFace ese día, y eso no es
    # reproducible. Se avisa en vez de forzarlo para no esconder la elección.
    print(f"    backend NLP: {settings.nlp_backend}")
    if settings.nlp_backend != "local":
        print("    ojo: en remoto esto NO es reproducible (usa NLP_BACKEND=local)")

    api = get_nlp_backend()

    async def correr() -> list[int]:
        out = []
        for i, h in enumerate(headlines, 1):
            r = await api.zero_shot(
                h, "facebook/bart-large-mnli", ["clickbait", "factual news"]
            )
            # Sin esta comprobación un fallo del proveedor a mitad de corrida
            # revienta con un TypeError opaco al indexar `data`, que es None, y
            # se pierden los minutos ya invertidos. Falla aquí y dice por qué.
            if not r.has_content():
                raise RuntimeError(
                    f"la señal falló en el titular {i}/{len(headlines)}: "
                    f"{r.error} (backend={settings.nlp_backend})"
                )
            out.append(int(r.data["label"] == "clickbait"))
            if i % 100 == 0:
                print(f"    ...{i}/{len(headlines)}", flush=True)
        return out

    veredictos = asyncio.run(correr())
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"headlines": headlines, "veredictos": veredictos}), encoding="utf-8"
    )
    return veredictos


def recall_por_intensidad(
    y: list[int],
    truth: list[float],
    predicciones: dict[str, list[int]],
    tramos: int = 3,
) -> list[dict]:
    """Recall sobre los positivos reales, por tercios de ``truthMean``.

    Sólo mira los positivos: en los negativos no hay recall que medir. La
    pregunta es si detectar clickbait se le da mejor a cada señal cuanto más
    flagrante lo consideraron los anotadores — es decir, si lo que aprendió
    responde a la intensidad del fenómeno o es indiferente a ella.
    """
    positivos = sorted(
        (
            {"truth": truth[i], **{n: p[i] for n, p in predicciones.items()}}
            for i in range(len(y))
            if y[i] == 1
        ),
        key=lambda d: d["truth"],
    )

    corte = len(positivos) // tramos
    grupos = [positivos[i * corte : (i + 1) * corte] for i in range(tramos)]
    # El último se lleva el resto para no perder muestras por el redondeo.
    grupos[-1] = positivos[(tramos - 1) * corte :]

    salida = []
    for grupo in grupos:
        fila = {
            "n": len(grupo),
            "truth_medio": sum(g["truth"] for g in grupo) / len(grupo),
        }
        for nombre in predicciones:
            fila[nombre] = sum(g[nombre] for g in grupo) / len(grupo)
        salida.append(fila)
    return salida


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %"


if __name__ == "__main__":
    cuantos = MUESTRA_POR_DEFECTO
    if "--muestra" in sys.argv:
        cuantos = int(sys.argv[sys.argv.index("--muestra") + 1])

    datos = load_external()
    y_todos = [y for _, y, _ in datos]
    print(f"Webis-17 completo: {len(datos)} titulares · {sum(y_todos)} clickbait")
    print(f"  tasa base (clase mayoritaria): {_pct(clase_mayoritaria(y_todos))}\n")

    # ------------------------------------------------------------------
    # Bloque 1 · corpus COMPLETO, sólo las señales que no cargan BART.
    # Son los números comparables con los de #76, que se midieron aquí.
    # ------------------------------------------------------------------
    print("CORPUS COMPLETO  (sin el zero-shot: 2459 titulares con BART son ~40 min)")
    h_todos = [h for h, _, _ in datos]
    preds = baratas(h_todos)
    print("  cargando el modelo dedicado...", flush=True)
    preds[f"dedicado ({DEDICADO.split('/')[-1][:22]})"] = dedicado(h_todos)

    print(f"\n  {'señal':38} {'acierto':>8} {'prec':>7} {'rec':>7} {'F1':>7}")
    for nombre, pred in preds.items():
        m = metricas(y_todos, pred)
        print(
            f"  {nombre:38} {_pct(m['acierto']):>8} {m['precision']:>7.3f} "
            f"{m['recall']:>7.3f} {m['f1']:>7.3f}"
        )

    # ------------------------------------------------------------------
    # Bloque 2 · muestra estratificada, con las CUATRO señales.
    # Aquí sí entra el zero-shot, y por eso todas se remiden sobre la misma
    # muestra: comparar su F1 con el del corpus completo de las otras sería
    # comparar dos conjuntos distintos.
    # ------------------------------------------------------------------
    muestra = muestra_estratificada(datos, cuantos)
    h_m = [h for h, _, _ in muestra]
    y_m = [y for _, y, _ in muestra]
    truth_m = [t for _, _, t in muestra]

    print(f"\n\nMUESTRA ESTRATIFICADA  ({len(h_m)} titulares, {sum(y_m)} clickbait)")
    print("  cargando bart-large-mnli...", flush=True)

    preds_m = baratas(h_m)
    preds_m["zero-shot (bart-large-mnli)"] = zero_shot_cacheado(
        h_m, f"webis_{len(h_m)}_24"
    )
    print("  cargando el modelo dedicado...", flush=True)
    preds_m["dedicado"] = dedicado(h_m)

    print(f"\n  {'señal':38} {'acierto':>8} {'prec':>7} {'rec':>7} {'F1':>7}")
    for nombre, pred in preds_m.items():
        m = metricas(y_m, pred)
        print(
            f"  {nombre:38} {_pct(m['acierto']):>8} {m['precision']:>7.3f} "
            f"{m['recall']:>7.3f} {m['f1']:>7.3f}"
        )
    print(f"\n  clase mayoritaria (no mirar): {_pct(clase_mayoritaria(y_m))}")
    print("  -> si varias señales caen cerca de ese número, el acierto no informa")

    # ------------------------------------------------------------------
    # Bloque 3 · ¿responde cada señal a la intensidad del clickbait?
    # ------------------------------------------------------------------
    print("\n\nRECALL POR INTENSIDAD  (tercios de `truthMean`, sólo positivos reales)")
    filas = recall_por_intensidad(y_m, truth_m, preds_m)
    nombres = list(preds_m)

    cabecera = f"  {'tramo':12} {'n':>4} {'truthMean':>10}"
    for nombre in nombres:
        cabecera += f" {nombre.split(' ')[0][:10]:>11}"
    print(cabecera)

    for etiqueta, fila in zip(("tibios", "medios", "flagrantes"), filas, strict=True):
        linea = f"  {etiqueta:12} {fila['n']:>4} {fila['truth_medio']:>10.2f}"
        for nombre in nombres:
            linea += f" {_pct(fila[nombre]):>11}"
        print(linea)

    print("\n  Un modelo que aprendió el CONCEPTO detecta mejor lo más flagrante.")
    print("  Uno que memorizó un corpus falla parejo en toda la escala.")
