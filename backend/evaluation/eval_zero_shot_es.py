"""¿Qué zero-shot sirve a la señal dedicada en español? (issue #232)

La señal dedicada (`detect_clickbait`) es un clasificador inglés, y en el Hub no
hay uno de clickbait en español fiable. Desde #159 la señal puede llamar a un
modelo de inferencia (NLI) como zero-shot, que no se entrenó para la tarea y
elige entre las etiquetas que se le preguntan; y desde #230 se le puede poner
uno para el español por configuración (`NLP_MODELS_ES`). Este guion mide qué
modelo, con qué etiquetas y con qué plantilla, en TA1C.

LO QUE SE COMBINA, fijado antes de medir (comentario en #232)

- Cuatro modelos: los dos multilingües de la issue y dos sólo en español,
  porque el enrutado ya es por idioma y un monolingüe sirve igual.
- Tres redacciones de las etiquetas. #159 midió que la redacción es parte de la
  pregunta: con BART, el mismo titular pasó de 0,701 a 0,987.
- Dos plantillas: la de `transformers`, «This example is {}.», que es la que usa
  hoy `local.zero_shot` porque no pasa ninguna, y una en español.

Cada combinación vota como en producción: la etiqueta más probable, que es la
primera que devuelve el pipeline y la que se queda `dedicated.detect`.

LAS DOS PARTES

    .venv/bin/python -m backend.evaluation.eval_zero_shot_es validation
    CUDA_VISIBLE_DEVICES= .venv/bin/python -m backend.evaluation.eval_zero_shot_es tiempo

- `validation`: las 24 combinaciones sobre TA1C `validation` (700). P, R y F1
  del voto, y la diferencia de F1 con la mejor, con su intervalo del 95 % por
  bootstrap emparejado (el de #78). El AUC va de información: el voto no tiene
  umbral que elegir. Cada combinación se guarda en `var/zero_shot_es/`, así que
  una ejecución que se corta sigue donde iba.
- `tiempo`: segundos por titular EN CPU, que es como corre producción, para la
  mejor combinación de cada modelo; se niega a medir si ve la GPU. Y aplica la
  regla de la issue: entre los modelos cuya mejor combinación queda dentro del
  ruido de la mejor de todas, el más rápido.

`test` NO se lee aquí. Se abre una sola vez, con la elegida, y si se queda (F1
al menos igual al del lineal en español) depende de #231.

POR QUÉ EL PIPELINE, Y NO `dedicated.detect`

`detect` devuelve sólo la etiqueta ganadora, y aquí hacen falta las dos
probabilidades (para el AUC) y la plantilla, que producción aún no deja
cambiar. Así que se llama al MISMO objeto que construye `LocalNLPClient`
(`_get_pipeline`), y con la plantilla de producción se comprueba sobre una
muestra que el voto coincide con el de `detect`: si no coincide, se para.
"""

import asyncio
import gc
import json
import re
import statistics
import sys
import time
from pathlib import Path

from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

from backend.evaluation.eval_reentreno import diferencia_con_intervalo
from backend.evaluation.splits import load_split
from backend.integrations.nlp import dedicated
from backend.integrations.nlp.local import LocalNLPClient

PARTE = "ta1c_validation"
CACHE = Path(__file__).resolve().parents[2] / "var" / "zero_shot_es"

CANDIDATOS = (
    "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
    "joeddav/xlm-roberta-large-xnli",
    "Recognai/bert-base-spanish-wwm-cased-xnli",
    "Recognai/zeroshot_selectra_medium",
)

# Lo que se le pregunta al modelo → la etiqueta del contrato, como `labels` en
# `NLP_MODELS_ES` (#159). Fijadas antes de medir.
REDACCIONES: dict[str, dict[str, str]] = {
    "palabras": {"clickbait": "clickbait", "noticia": "factual news"},
    "adjetivos": {"sensacionalista": "clickbait", "informativo": "factual news"},
    "frases": {
        "un titular que oculta información para provocar el clic": "clickbait",
        "un titular que resume la noticia": "factual news",
    },
}

PLANTILLAS = {
    # La de `transformers` (`ZeroShotClassificationPipeline.preprocess`): la que
    # usa producción hoy. La comprobación de paridad lo confirma.
    "inglesa": "This example is {}.",
    "espanola": "Este titular es {}.",
}

MUESTRA_PARIDAD = 30
MUESTRA_TIEMPO = 100
CALENTAMIENTO = 3


def _nombre(modelo: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", modelo)


def _pregunta_del_clickbait(preguntas: dict[str, str]) -> str:
    return next(
        pregunta for pregunta, etiqueta in preguntas.items() if etiqueta == "clickbait"
    )


def _cargar(cliente: LocalNLPClient, modelo: str):
    """El pipeline de producción para un modelo, comprobando que es de NLI."""
    inicio = time.perf_counter()
    pipe = cliente._get_pipeline(dedicated.ZERO_SHOT, modelo)
    if getattr(pipe, "entailment_id", None) == -1:
        raise SystemExit(f"{modelo} no es de inferencia (NLI): no sirve como zero-shot")
    print(
        f"\n== {modelo}: cargado en {time.perf_counter() - inicio:.1f} s, en {pipe.device}",
        flush=True,
    )
    return pipe


def _liberar() -> None:
    gc.collect()
    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def probabilidades(
    pipe, titulares: list[str], preguntas: dict[str, str], plantilla: str
) -> list[float]:
    """La probabilidad que el modelo da a la pregunta del clickbait, titular a
    titular. Con dos preguntas, las dos suman 1: votar la más probable es votar
    clickbait por encima de 0,5."""
    del_clickbait = _pregunta_del_clickbait(preguntas)
    salidas = pipe(
        titulares, candidate_labels=list(preguntas), hypothesis_template=plantilla
    )
    return [
        dict(zip(salida["labels"], salida["scores"], strict=True))[del_clickbait]
        for salida in salidas
    ]


async def _comprobar_paridad(
    cliente: LocalNLPClient, pipe, modelo: str, muestra: list[str]
) -> None:
    """Con la plantilla de producción, el voto de aquí tiene que ser el de
    `dedicated.detect`, titular a titular. Si no, lo medido no sería la señal."""
    for preguntas in REDACCIONES.values():
        aqui = probabilidades(pipe, muestra, preguntas, PLANTILLAS["inglesa"])
        for titular, probabilidad in zip(muestra, aqui, strict=True):
            resultado = await dedicated.detect(
                cliente, titular, modelo, dedicated.ZERO_SHOT, preguntas
            )
            if not resultado.has_content():
                raise SystemExit(f"`detect` falló con {modelo}: {resultado.error}")
            esperada = "clickbait" if probabilidad > 0.5 else "factual news"
            if resultado.data["label"] != esperada:
                raise SystemExit(
                    f"PARIDAD ROTA con {modelo}: «{titular}» da {resultado.data['label']} "
                    f"en `detect` y {esperada} aquí ({probabilidad:.4f})"
                )
    print(
        f"  paridad con `dedicated.detect`: {len(muestra)} titulares × {len(REDACCIONES)} redacciones, iguales",
        flush=True,
    )


def _leer(ruta: Path, preguntas: dict[str, str], plantilla: str, cuantos: int):
    """Una combinación ya medida, si lo guardado es de esta misma pregunta."""
    if not ruta.exists():
        return None
    guardado = json.loads(ruta.read_text(encoding="utf-8"))
    if (
        guardado["preguntas"] != preguntas
        or guardado["plantilla"] != plantilla
        or len(guardado["probabilidades"]) != cuantos
    ):
        return None
    return guardado


def validation() -> None:
    pares = load_split(PARTE)
    titulares = [titular for titular, _ in pares]
    etiquetas = [etiqueta for _, etiqueta in pares]
    CACHE.mkdir(parents=True, exist_ok=True)
    clickbait = sum(etiquetas)
    print(
        f"== TA1C validation: {len(pares)} titulares, {clickbait} clickbait ({clickbait / len(pares):.1%})",
        flush=True,
    )

    resultados = []
    for modelo in CANDIDATOS:
        cliente = LocalNLPClient()
        pipe = None
        for redaccion, preguntas in REDACCIONES.items():
            for plantilla, texto_plantilla in PLANTILLAS.items():
                ruta = CACHE / f"{_nombre(modelo)}__{redaccion}__{plantilla}.json"
                guardado = _leer(ruta, preguntas, texto_plantilla, len(titulares))
                if guardado is None:
                    if pipe is None:
                        pipe = _cargar(cliente, modelo)
                        asyncio.run(
                            _comprobar_paridad(
                                cliente, pipe, modelo, titulares[:MUESTRA_PARIDAD]
                            )
                        )
                    inicio = time.perf_counter()
                    medidas = probabilidades(
                        pipe, titulares, preguntas, texto_plantilla
                    )
                    guardado = {
                        "modelo": modelo,
                        "revision": getattr(pipe.model.config, "_commit_hash", None),
                        "redaccion": redaccion,
                        "preguntas": preguntas,
                        "plantilla": texto_plantilla,
                        "nombre_plantilla": plantilla,
                        "dispositivo": str(pipe.device),
                        "segundos": round(time.perf_counter() - inicio, 1),
                        "probabilidades": medidas,
                    }
                    ruta.write_text(
                        json.dumps(guardado, ensure_ascii=False), encoding="utf-8"
                    )
                    print(
                        f"  {redaccion} · {plantilla}: {guardado['segundos']} s",
                        flush=True,
                    )
                resultados.append(guardado)
        del cliente, pipe
        _liberar()

    informe(etiquetas, resultados)


def informe(etiquetas: list[int], resultados: list[dict]) -> None:
    prevalencia = sum(etiquetas) / len(etiquetas)
    print(
        f"\n== referencia: votar «clickbait» siempre da F1 {2 * prevalencia / (1 + prevalencia):.3f}"
    )

    medidas = []
    for resultado in resultados:
        votos = [
            int(probabilidad > 0.5) for probabilidad in resultado["probabilidades"]
        ]
        precision, recall, f1, _ = precision_recall_fscore_support(
            etiquetas, votos, average="binary", zero_division=0
        )
        medidas.append(
            {
                "modelo": resultado["modelo"],
                "revision": resultado["revision"],
                "redaccion": resultado["redaccion"],
                "plantilla": resultado["nombre_plantilla"],
                "votos": votos,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "votan_clickbait": sum(votos) / len(votos),
                "auc": roc_auc_score(etiquetas, resultado["probabilidades"]),
            }
        )
    medidas.sort(key=lambda medida: medida["f1"], reverse=True)
    mejor = medidas[0]

    print("\n== las 24 combinaciones, de mayor a menor F1")
    print(
        f"  {'modelo':42} {'redacción':10} {'plantilla':9}    P      R     F1   vota cb   AUC   ΔF1 con la mejor [IC 95 %]"
    )
    for medida in medidas:
        if medida is mejor:
            medida["empata"] = True
            diferencia = "—"
        else:
            delta, bajo, alto = diferencia_con_intervalo(
                etiquetas, mejor["votos"], medida["votos"]
            )
            medida["empata"] = bajo <= 0
            diferencia = f"{-delta:+.3f} [{-alto:+.3f}, {-bajo:+.3f}]" + (
                " (dentro del ruido)" if medida["empata"] else ""
            )
        print(
            f"  {medida['modelo']:42} {medida['redaccion']:10} {medida['plantilla']:9}"
            f" {medida['precision']:.3f}  {medida['recall']:.3f}  {medida['f1']:.3f}"
            f"   {medida['votan_clickbait']:6.1%}  {medida['auc']:.3f}   {diferencia}"
        )

    # La lista va de mayor a menor F1: la primera de cada modelo es su mejor.
    mejores: dict[str, dict] = {}
    for medida in medidas:
        mejores.setdefault(medida["modelo"], medida)
    print("\n== la mejor combinación de cada modelo")
    for modelo, medida in mejores.items():
        print(
            f"  {modelo:42} {medida['redaccion']:10} {medida['plantilla']:9} F1 {medida['f1']:.3f}"
            + ("  · empata con la mejor" if medida["empata"] else "")
        )

    resumen = {
        "parte": PARTE,
        "mejores": {
            modelo: {
                clave: medida[clave]
                for clave in (
                    "revision",
                    "redaccion",
                    "plantilla",
                    "precision",
                    "recall",
                    "f1",
                    "auc",
                    "empata",
                )
            }
            for modelo, medida in mejores.items()
        },
    }
    (CACHE / "validation.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "\n  (El tiempo en CPU y la elección: `CUDA_VISIBLE_DEVICES= … eval_zero_shot_es tiempo`.)"
    )


def tiempo() -> None:
    import torch

    if torch.cuda.is_available():
        raise SystemExit(
            "La GPU está a la vista: lánzalo con CUDA_VISIBLE_DEVICES= para medir en CPU, como producción."
        )
    resumen = json.loads((CACHE / "validation.json").read_text(encoding="utf-8"))
    titulares = [titular for titular, _ in load_split(PARTE)[:MUESTRA_TIEMPO]]
    with open("/proc/cpuinfo", encoding="utf-8") as fichero:
        procesador = next(
            linea.split(":", 1)[1].strip()
            for linea in fichero
            if linea.startswith("model name")
        )
    print(
        f"== CPU: {procesador}, {torch.get_num_threads()} hilos de torch; {len(titulares)} titulares, uno a uno como en producción",
        flush=True,
    )

    medidos = {}
    for modelo, mejor in resumen["mejores"].items():
        cliente = LocalNLPClient()
        inicio = time.perf_counter()
        pipe = cliente._get_pipeline(dedicated.ZERO_SHOT, modelo)
        carga = time.perf_counter() - inicio
        preguntas = list(REDACCIONES[mejor["redaccion"]])
        plantilla = PLANTILLAS[mejor["plantilla"]]
        for titular in titulares[:CALENTAMIENTO]:
            pipe(titular, candidate_labels=preguntas, hypothesis_template=plantilla)
        segundos = []
        for titular in titulares:
            inicio = time.perf_counter()
            pipe(titular, candidate_labels=preguntas, hypothesis_template=plantilla)
            segundos.append(time.perf_counter() - inicio)
        segundos.sort()
        medidos[modelo] = {
            "carga_s": round(carga, 1),
            "mediana_s": statistics.median(segundos),
            "p95_s": segundos[int(0.95 * len(segundos)) - 1],
            "dispositivo": str(pipe.device),
        }
        print(
            f"  {modelo:42} carga {carga:5.1f} s · por titular: mediana {medidos[modelo]['mediana_s']:.3f} s, p95 {medidos[modelo]['p95_s']:.3f} s ({pipe.device})",
            flush=True,
        )
        del cliente, pipe
        _liberar()

    empatados = [
        modelo for modelo, mejor in resumen["mejores"].items() if mejor["empata"]
    ]
    elegido = min(empatados, key=lambda modelo: medidos[modelo]["mediana_s"])
    mejor = resumen["mejores"][elegido]
    print(
        f"\n== ELEGIDA por la regla: {elegido} · {mejor['redaccion']} · plantilla {mejor['plantilla']}"
        f" (F1 {mejor['f1']:.3f} en validation; {medidos[elegido]['mediana_s']:.3f} s por titular en CPU)"
    )
    print(f"  empatadas con la mejor: {', '.join(empatados)}")
    (CACHE / "tiempo.json").write_text(
        json.dumps(
            {
                "procesador": procesador,
                "hilos": torch.get_num_threads(),
                "modelos": medidos,
                "elegido": elegido,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parte = sys.argv[1] if len(sys.argv) > 1 else ""
    if parte == "validation":
        validation()
    elif parte == "tiempo":
        tiempo()
    else:
        raise SystemExit(
            "Uso: python -m backend.evaluation.eval_zero_shot_es [validation | tiempo]"
        )


if __name__ == "__main__":
    main()
