"""¿Quién ocupa la tercera plaza de `forma`? (issue #115)

`detect_clickbait` usa `facebook/bart-large-mnli`, elegido en E3-02 **por
eliminación**: era lo único que el serverless de HuggingFace servía para esto. La
condición del aplazamiento —«si llega la infra»— se cumplió en la Épica 5 con
`LocalNLPClient`, y nadie volvió a la nota. #109 midió el coste: 63,7 % de
acierto, la señal más floja de la dimensión.

Esto compara candidatos para sustituirlo. **No basta con que acierten más.**

LOS TRES CRITERIOS, y por qué son tres

1. **Acierto fuera de dominio**, contra la clase mayoritaria y no en absoluto. Con
   Webis al 69 % de negativos, responder «no» a todo ya da 69 %.

2. **Independencia del par acoplado.** Un candidato preciso que coincida con
   léxico+lineal no aporta nada: la plaza no necesita otra confirmación, necesita
   una señal capaz de discrepar con fundamento. Sin este criterio se elegiría el
   más exacto, que puede ser justamente el más redundante.

3. **Ausencia de memorización.** `elozano/bert-base-cased-clickbait-news` sacó un
   99,7 % en Chakraborty y un F1 de 0,185 en Webis: había memorizado el corpus con
   el que lo medíamos. De ahí el campo ``entrenado_en``, que no es documentación
   sino **lo que decide en qué corpus se le evalúa**: a cada candidato se le juzga
   por el material que NO vio. Para los que no declaran su dataset, el patrón
   —alto en uno, desplome en el otro— sigue delatándolo.

Los dos corpus miden cosas distintas y por eso se conservan los dos: Chakraborty
etiqueta **por fuente** (BuzzFeed = clickbait) y Webis por **juicio humano**
(`truthMean`). Un modelo entrenado en el primero puede lucir sin haber aprendido
clickbait; ninguno entrenado en el segundo puede evaluarse honestamente en él.

    NLP_BACKEND=local python -m backend.evaluation.eval_candidatos
"""

import json
from dataclasses import dataclass
from pathlib import Path

# Se importan los MÓDULOS y no sus funciones porque ambos exportan una
# `muestra_estratificada` distinta —una estratifica pares, la otra ternas con
# `truthMean`— y con el prefijo delante se ve cuál es cuál en el punto de uso.
from backend.evaluation import eval_acoplamiento as acopl
from backend.evaluation import eval_transferencia as transf
from backend.evaluation.eval_external import load_external
from backend.evaluation.splits import load_split

_RAIZ = Path(__file__).resolve().parents[2]

SEMILLA = 24
N_CHAKRABORTY = 300  # la misma muestra de #109, para que el kappa sea comparable
N_WEBIS = 600

# Sonda para fijar el mapeo de etiquetas de los clasificadores: las convenciones
# no están normalizadas entre modelos y cablear el positivo al revés invertiría
# el resultado sin que ninguna excepción avisara.
SONDA_CLICKBAIT = "17 Things Nobody Tells You About Working From Home"
SONDA_FACTUAL = "Federal Reserve raises interest rates by 0.25 percent"

ETIQUETAS_ZS = ["clickbait", "factual news"]


@dataclass(frozen=True)
class Candidato:
    """Un modelo a evaluar, con lo que hace falta para juzgarlo con justicia.

    ``entrenado_en`` es el campo que gobierna la comparación: nombra el corpus que
    el modelo YA VIO, y por tanto aquel en el que su puntuación no significa nada.
    ``None`` significa que no vio ninguno de los dos —el caso de los NLI
    genéricos—, y entonces ambos corpus son test honesto.
    """

    alias: str
    modelo: str
    modo: str  # "zero-shot" | "clasificacion"
    entrenado_en: str | None
    nota: str = ""

    def honesto(self, corpus: str) -> bool:
        return self.entrenado_en != corpus


CANDIDATOS: tuple[Candidato, ...] = (
    Candidato(
        alias="INCUMBENTE bart-large-mnli",
        modelo="facebook/bart-large-mnli",
        modo="zero-shot",
        entrenado_en=None,
        nota="elegido en E3-02 por eliminación; línea base a batir",
    ),
    Candidato(
        alias="Stremie roberta-base",
        modelo="Stremie/roberta-base-clickbait",
        modo="clasificacion",
        entrenado_en="webis",
        nota="declara Webis-Clickbait-17: entrenado con ETIQUETA HUMANA, no por fuente",
    ),
    Candidato(
        alias="DeBERTa-v3-base NLI",
        modelo="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
        modo="zero-shot",
        entrenado_en=None,
        nota="NLI más fuerte que BART; conserva la inmunidad al sesgo de fuente",
    ),
)


def _clave_cache(cand: Candidato, corpus: str, n: int) -> str:
    """Nombre del fichero de caché.

    El incumbente reutiliza las claves que ya escribieron #109 y
    `eval_transferencia`: son las mismas predicciones sobre las mismas muestras,
    y recalcularlas serían minutos de BART tirados.
    """
    if cand.modelo == "facebook/bart-large-mnli":
        legado = {
            "chakraborty": f"zero_shot_dev_{n}_{SEMILLA}",
            "webis": f"zero_shot_webis_{n}_{SEMILLA}",
        }
        return legado[corpus]
    slug = cand.modelo.replace("/", "_")
    return f"cand_{slug}_{corpus}_{n}_{SEMILLA}"


def _cacheado(clave: str, headlines: list[str], calcular) -> list[int]:
    """Caché en disco con verificación de que corresponde a ESTA muestra.

    Se comparan los titulares y no sólo el nombre del fichero: una clave que
    coincidiera por casualidad daría un resultado equivocado en silencio, que es
    peor que no tener caché.
    """
    fichero = _RAIZ / "var" / f"{clave}.json"
    if fichero.exists():
        guardado = json.loads(fichero.read_text(encoding="utf-8"))
        if guardado["headlines"] == headlines:
            print(f"      (reusando {fichero.name})")
            return guardado["veredictos"]
        print(f"      ({fichero.name} no corresponde a esta muestra: recalculando)")

    veredictos = calcular()
    fichero.parent.mkdir(parents=True, exist_ok=True)
    fichero.write_text(
        json.dumps({"headlines": headlines, "veredictos": veredictos}), encoding="utf-8"
    )
    return veredictos


def predecir(cand: Candidato, headlines: list[str], corpus: str) -> list[int]:
    """Veredictos 0/1 del candidato, con caché."""

    def calcular() -> list[int]:
        from transformers import pipeline

        if cand.modo == "zero-shot":
            pipe = pipeline("zero-shot-classification", model=cand.modelo)
            salida = pipe(headlines, candidate_labels=ETIQUETAS_ZS)
            return [int(s["labels"][0] == "clickbait") for s in salida]

        pipe = pipeline("text-classification", model=cand.modelo)
        sonda = pipe([SONDA_CLICKBAIT, SONDA_FACTUAL])
        if sonda[0]["label"] == sonda[1]["label"]:
            raise RuntimeError(
                f"{cand.modelo}: la sonda no separa los dos casos ({sonda}); "
                "el mapeo de etiquetas no se puede fijar automáticamente"
            )
        positiva = sonda[0]["label"]
        print(f"      etiqueta positiva: «{positiva}»")
        return [int(s["label"] == positiva) for s in pipe(headlines)]

    print(f"    {cand.alias} sobre {corpus} ({len(headlines)})...", flush=True)
    return _cacheado(_clave_cache(cand, corpus, len(headlines)), headlines, calcular)


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %"


if __name__ == "__main__":
    # --- las dos muestras, con las mismas semillas que #109 ---
    dev = acopl.muestra_estratificada(load_split("dev"), N_CHAKRABORTY, semilla=SEMILLA)
    webis = transf.muestra_estratificada(load_external(), N_WEBIS, semilla=SEMILLA)

    corpus = {
        "chakraborty": {
            "headlines": [p[0] for p in dev],
            "y": [p[1] for p in dev],
            "truth": None,
            "etiqueta": "por FUENTE (BuzzFeed = clickbait)",
        },
        "webis": {
            "headlines": [d[0] for d in webis],
            "y": [d[1] for d in webis],
            "truth": [d[2] for d in webis],
            "etiqueta": "por JUICIO HUMANO (truthMean)",
        },
    }

    print("LAS DOS MUESTRAS")
    for nombre, c in corpus.items():
        base = transf.clase_mayoritaria(c["y"])
        print(
            f"  {nombre:12} n={len(c['y']):>4}  positivos {_pct(sum(c['y']) / len(c['y']))}"
            f"  ·  mayoritaria {_pct(base)}  ·  etiqueta {c['etiqueta']}"
        )

    # El par acoplado, para medir independencia. Se calcula una vez por corpus.
    for c in corpus.values():
        c["lex"], c["lin"] = acopl.predicciones(c["headlines"])

    print("\n\nEVALUACIÓN")
    resumen = []
    for cand in CANDIDATOS:
        print(f"\n{'=' * 78}\n{cand.alias}  ·  {cand.modelo}")
        if cand.nota:
            print(f"  {cand.nota}")
        visto = cand.entrenado_en or "ninguno de los dos"
        print(f"  entrenado en: {visto}")
        print(f"{'=' * 78}")

        print(f"\n  {'corpus':26} {'acierto':>8} {'prec':>7} {'rec':>7} {'F1':>7}")
        for nombre, c in corpus.items():
            pred = predecir(cand, c["headlines"], nombre)
            m = transf.metricas(c["y"], pred)
            marca = "" if cand.honesto(nombre) else "  <- CONTAMINADO (lo vio)"
            print(
                f"  {nombre:26} {_pct(m['acierto']):>8} {m['precision']:>7.3f} "
                f"{m['recall']:>7.3f} {m['f1']:>7.3f}{marca}"
            )
            c[cand.alias] = pred
            if cand.honesto(nombre):
                resumen.append((cand.alias, nombre, m))

        # --- criterio 2: ¿discrepa del par acoplado, o lo confirma? ---
        print("\n  INDEPENDENCIA en el test honesto (kappa contra el par acoplado)")
        for nombre, c in corpus.items():
            if not cand.honesto(nombre):
                continue
            for otra in ("lex", "lin"):
                a = acopl.acuerdo(c[cand.alias], c[otra])
                nombre_otra = "lexical" if otra == "lex" else "linear"
                print(
                    f"    {nombre:12} vs {nombre_otra:8} acuerdo {_pct(a['observado']):>8}"
                    f"   kappa {a['kappa']:>6.3f}"
                )

    # --- criterio 3 aplicado: respuesta a la intensidad, donde Webis es honesto ---
    print(
        f"\n\n{'=' * 78}\nRESPUESTA A LA INTENSIDAD (tercios de `truthMean`, solo positivos)"
    )
    print(f"{'=' * 78}")
    c = corpus["webis"]
    honestos = {
        cand.alias: c[cand.alias] for cand in CANDIDATOS if cand.honesto("webis")
    }
    honestos["lexical"] = c["lex"]
    filas = transf.recall_por_intensidad(c["y"], c["truth"], honestos)

    cabecera = f"  {'tramo':12} {'n':>4} {'truthMean':>10}"
    for nombre in honestos:
        cabecera += f" {nombre[:13]:>14}"
    print(cabecera)
    for etiqueta, fila in zip(("tibios", "medios", "flagrantes"), filas, strict=True):
        linea = f"  {etiqueta:12} {fila['n']:>4} {fila['truth_medio']:>10.2f}"
        for nombre in honestos:
            linea += f" {_pct(fila[nombre]):>14}"
        print(linea)

    print("\n\nRESUMEN · sólo tests honestos")
    print(f"  {'candidato':28} {'corpus':14} {'F1':>7} {'acierto':>9}")
    for alias, nombre, m in resumen:
        print(f"  {alias:28} {nombre:14} {m['f1']:>7.3f} {_pct(m['acierto']):>9}")
    print("\n  Recuerda los tres criterios: acierto fuera de dominio, INDEPENDENCIA")
    print("  del par acoplado, y ausencia del patrón de memorización.")
