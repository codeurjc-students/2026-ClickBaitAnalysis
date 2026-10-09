"""¿Sirve a la dedicada en español un BETO afinado con TA1C? (issue #242)

En #232 ningún zero-shot multilingüe llegó al lineal en español: XLM-R dio
0,450 en TA1C `test`, frente a 0,674. El autor eligió afinar un modelo en
español con TA1C, la base que los autores del corpus publican con 0,84. Este
guion lo afina, lo mide y aplica la regla publicada en la issue antes de medir.

EL RIESGO DE FUENTE, Y LAS DOS ACOTACIONES

La proporción de clickbait cambia mucho de un medio a otro, y los 18 medios
están en las tres partes de TA1C (`spikes/ta1c_medios.py`): un modelo puede
acertar en `test` reconociendo al medio. El autor eligió dos acotaciones:

- LIMPIAR al entrenar los enlaces, las cuentas (`@…`), las etiquetas (`#…`,
  con su palabra), los corchetes y las barras «|», que es donde `train` lleva
  las marcas del medio (`#diariolibre` en 94 de 100 tuits). Es mecánica y sin
  lista de medios, así que vale igual para uno que no se ha visto. Producción
  recibe el titular tal cual, y así se mide `test`.
- MEDIOS FUERA: seis pliegues de tres medios sobre `train` + `validation`; en
  cada uno, BETO y el lineal se entrenan con los otros quince medios y se miden
  en esos tres.

LO FIJADO ANTES DE MEDIR (issue y regla de #242)

BETO cased (`dccuchile/bert-base-spanish-wwm-cased`, revisión fijada), un
bucle propio en PyTorch (el `.venv` no tiene `accelerate`): AdamW con tasa
2e-5 y decaimiento 0,01, lote 16, tres épocas, calentamiento lineal del 10 %,
recorte del gradiente a 1, 128 tokens con relleno por lote y fp16 en la GPU.
Tres semillas. Vota la etiqueta más probable, como la dedicada inglesa.

LAS PARTES

    .venv/bin/python -m backend.evaluation.eval_dedicada_es memoria
    .venv/bin/python -m backend.evaluation.eval_dedicada_es validation
    .venv/bin/python -m backend.evaluation.eval_dedicada_es medios-fuera
    .venv/bin/python -m backend.evaluation.eval_dedicada_es test
    CUDA_VISIBLE_DEVICES= .venv/bin/python -m backend.evaluation.eval_dedicada_es tiempo

- `memoria`: unos pasos de entrenamiento con los tuits más largos de `train`,
  y el pico de memoria de la GPU. No mira ningún resultado: decide el lote.
- `validation`: cada semilla, entrenada limpia y tal cual, y medida con la
  entrada tal cual y limpia. Se elige la semilla de mejor F1 en la
  configuración de producción (entrenada limpia, entrada tal cual); en un
  empate, la menor.
- `medios-fuera`: la parte (b) de la regla.
- `test`: la elegida, UNA vez, con la parte (a) y el veredicto de la regla.
- `tiempo`: segundos por titular EN CPU, como producción.

POR QUÉ SE GUARDAN LOS PESOS, Y NO HAY `train_dedicada_es.py`

Entrenar en la GPU no repite el modelo bit a bit con la misma semilla, así que
reentrenar daría otro modelo que el medido. `validation` guarda el de cada
semilla entrenada limpia en `var/dedicada_es/modelos/`, y `test`, `tiempo` y
lo que se publique usan ésos: lo publicado es lo medido.
"""

import asyncio
import gc
import gzip
import json
import math
import random
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import torch
import transformers
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

from backend.evaluation.eval_lineal_es import FEATURIZACION, UMBRAL_DE_LA_ELEGIDA
from backend.evaluation.eval_reentreno import (
    cargar_datos,
    diferencia_con_intervalo,
    entrenar,
)
from backend.evaluation.ta1c_extract import DESTINO_TEASERS
from backend.integrations.nlp import dedicated, linear
from backend.integrations.nlp.local import LocalNLPClient

BASE = "dccuchile/bert-base-spanish-wwm-cased"
REVISION = "c4d86612f51b"  # la descargada el 9 oct
CACHE = Path(__file__).resolve().parents[2] / "var" / "dedicada_es"
MODELOS = CACHE / "modelos"

# Fijados antes de medir (ver el docstring).
SEMILLAS = (0, 1, 2)
TASA = 2e-5
DECAIMIENTO = 0.01
LOTE = 16
# Si la GPU no aguanta el lote entero, se parte en trozos y se acumula el
# gradiente: el lote efectivo y las cuentas son los mismos. Lo fija `memoria`.
TROZOS_POR_LOTE = 1
EPOCAS = 3
CALENTAMIENTO = 0.1
RECORTE = 1.0
MAX_TOKENS = 128

# Las etiquetas del modelo son las que `dedicated.ETIQUETAS` ya traduce al
# contrato: la ficha no tendrá que configurar ninguna.
ETIQUETAS_DEL_MODELO = {0: "Not Clickbait", 1: "Clickbait"}

# La regla (comentario en #242).
LISTON_TEST = 0.674  # el lineal en español en TA1C `test` (#231)
UMBRAL_LINEAL = UMBRAL_DE_LA_ELEGIDA  # 0,35, el de producción

# Seis pliegues de tres medios, en serpiente por tamaño en train + validation.
PLIEGUES = (
    ("Clarín", "El Comercio", "El Universal México"),
    ("infobae", "El Tiempo", "El País"),
    ("El País Madrid", "Diario Libre", "La Prensa Gráfica"),
    ("El Mundo", "La Tercera", "La Nación"),
    ("Prensa Libre", "El Comercio Perú", "La Vanguardia"),
    ("abc", "El Universal Venezuela", "BBC"),
)

MUESTRA_PARIDAD = 30
MUESTRA_TIEMPO = 100
CALENTAMIENTO_TIEMPO = 3
PASOS_DE_MEMORIA = 20

# Lo que se quita al entrenar. Sin lista de medios: la forma de la marca.
MARCAS = re.compile(r"https?://\S+|www\.\S+|[@#]\w+|\[[^\]]{1,40}\]|\|")


def limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", MARCAS.sub(" ", texto)).strip()


def ta1c(parte: str) -> list[dict]:
    with gzip.open(DESTINO_TEASERS, "rt", encoding="utf-8") as fichero:
        return [fila for fila in map(json.loads, fichero) if fila["parte"] == parte]


def _dispositivo() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _liberar() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _condiciones() -> dict:
    return {
        "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base": BASE,
        "revision": REVISION,
        "dispositivo": str(_dispositivo()),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "hiperparametros": {
            "tasa": TASA,
            "decaimiento": DECAIMIENTO,
            "lote": LOTE,
            "trozos_por_lote": TROZOS_POR_LOTE,
            "epocas": EPOCAS,
            "calentamiento": CALENTAMIENTO,
            "recorte": RECORTE,
            "max_tokens": MAX_TOKENS,
        },
    }


def afinar(
    textos: list[str],
    etiquetas: list[int],
    semilla: int,
    pasos_maximos: int | None = None,
):
    """BETO afinado con estos tuits. Devuelve el tokenizador y el modelo."""
    torch.manual_seed(semilla)
    azar = random.Random(semilla)
    dispositivo = _dispositivo()
    en_gpu = dispositivo.type == "cuda"
    tokenizador = AutoTokenizer.from_pretrained(BASE, revision=REVISION)
    modelo = AutoModelForSequenceClassification.from_pretrained(
        BASE,
        revision=REVISION,
        num_labels=2,
        id2label=ETIQUETAS_DEL_MODELO,
        label2id={
            etiqueta: indice for indice, etiqueta in ETIQUETAS_DEL_MODELO.items()
        },
    ).to(dispositivo)

    pasos = math.ceil(len(textos) / LOTE) * EPOCAS
    optimizador = torch.optim.AdamW(
        modelo.parameters(), lr=TASA, weight_decay=DECAIMIENTO
    )
    planificador = get_linear_schedule_with_warmup(
        optimizador, int(CALENTAMIENTO * pasos), pasos
    )
    escalador = torch.amp.GradScaler(enabled=en_gpu)
    por_trozo = math.ceil(LOTE / TROZOS_POR_LOTE)

    modelo.train()
    orden = list(range(len(textos)))
    paso = 0
    for _ in range(EPOCAS):
        azar.shuffle(orden)
        for inicio in range(0, len(orden), LOTE):
            lote = orden[inicio : inicio + LOTE]
            optimizador.zero_grad()
            for desde in range(0, len(lote), por_trozo):
                trozo = lote[desde : desde + por_trozo]
                entrada = tokenizador(
                    [textos[indice] for indice in trozo],
                    truncation=True,
                    max_length=MAX_TOKENS,
                    padding=True,
                    return_tensors="pt",
                ).to(dispositivo)
                objetivo = torch.tensor(
                    [etiquetas[indice] for indice in trozo], device=dispositivo
                )
                with torch.autocast(
                    dispositivo.type, dtype=torch.float16, enabled=en_gpu
                ):
                    # La media del lote entero, aunque llegue en trozos.
                    perdida = (
                        modelo(**entrada, labels=objetivo).loss * len(trozo) / len(lote)
                    )
                escalador.scale(perdida).backward()
            escalador.unscale_(optimizador)
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), RECORTE)
            escalador.step(optimizador)
            escalador.update()
            planificador.step()
            paso += 1
            if pasos_maximos is not None and paso >= pasos_maximos:
                return tokenizador, modelo
    return tokenizador, modelo


def probabilidades(
    tokenizador, modelo, textos: list[str], lote: int = 64
) -> list[float]:
    """La probabilidad de «Clickbait» de cada tuit, en fp32 como producción."""
    modelo.eval()
    dispositivo = next(modelo.parameters()).device
    salida: list[float] = []
    with torch.no_grad():
        for inicio in range(0, len(textos), lote):
            entrada = tokenizador(
                textos[inicio : inicio + lote],
                truncation=True,
                max_length=MAX_TOKENS,
                padding=True,
                return_tensors="pt",
            ).to(dispositivo)
            logits = modelo(**entrada).logits.float()
            salida += torch.softmax(logits, dim=-1)[:, 1].tolist()
    return salida


def medida(
    etiquetas: list[int],
    probabilidades_clickbait: list[float],
    umbral: float | None = None,
) -> dict:
    """Sin umbral, la etiqueta más probable (> 0,5), como BETO; con él, como el lineal."""
    votos = [
        int(probabilidad >= umbral if umbral is not None else probabilidad > 0.5)
        for probabilidad in probabilidades_clickbait
    ]
    precision, recall, f1, _ = precision_recall_fscore_support(
        etiquetas, votos, average="binary", zero_division=0
    )
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "votan_clickbait": sum(votos) / len(votos),
        "auc": roc_auc_score(etiquetas, probabilidades_clickbait),
        "votos": votos,
    }


def _linea(nombre: str, resultado: dict) -> str:
    return (
        f"  {nombre:44} P {resultado['precision']:.3f} · R {resultado['recall']:.3f} · "
        f"F1 {resultado['f1']:.3f} · vota cb {resultado['votan_clickbait']:.1%} · "
        f"AUC {resultado['auc']:.3f}"
    )


def _leer(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def _escribir(ruta: Path, datos: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def memoria() -> None:
    if not torch.cuda.is_available():
        raise SystemExit("`memoria` mide la GPU, y no se ve ninguna.")
    filas = sorted(ta1c("train"), key=lambda fila: len(fila["headline"]), reverse=True)
    peores = filas[: LOTE * PASOS_DE_MEMORIA]
    libre, total = torch.cuda.mem_get_info()
    print(
        f"== {torch.cuda.get_device_name(0)}: {libre / 2**20:.0f} MiB libres de {total / 2**20:.0f}; "
        f"lote {LOTE} en {TROZOS_POR_LOTE} trozo(s), {MAX_TOKENS} tokens como máximo",
        flush=True,
    )
    print(
        f"  {PASOS_DE_MEMORIA} pasos con los {len(peores)} tuits más largos de train, tal cual "
        "(el peor caso: limpios son más cortos). No se mide ningún resultado.",
        flush=True,
    )
    torch.cuda.reset_peak_memory_stats()
    inicio = time.perf_counter()
    try:
        afinar(
            [fila["headline"] for fila in peores],
            [fila["label"] for fila in peores],
            semilla=0,
            pasos_maximos=PASOS_DE_MEMORIA,
        )
    except torch.OutOfMemoryError:
        raise SystemExit(
            "NO CABE: sube TROZOS_POR_LOTE (2: trozos de 8) y repite."
        ) from None
    torch.cuda.synchronize()
    segundos = time.perf_counter() - inicio
    pasos = math.ceil(len(filas) / LOTE) * EPOCAS
    print(
        f"  pico: {torch.cuda.max_memory_allocated() / 2**20:.0f} MiB asignados, "
        f"{torch.cuda.max_memory_reserved() / 2**20:.0f} MiB reservados, de {total / 2**20:.0f}"
    )
    print(
        f"  {segundos:.1f} s para {PASOS_DE_MEMORIA} pasos (con la carga del modelo); "
        f"un entrenamiento son {pasos} pasos"
    )


def validation() -> None:
    train = ta1c("train")
    validacion = ta1c("validation")
    etiquetas_train = [fila["label"] for fila in train]
    titulares = [fila["headline"] for fila in validacion]
    etiquetas = [fila["label"] for fila in validacion]
    limpios = [limpiar(titular) for titular in titulares]

    for semilla in SEMILLAS:
        for entrenado_limpio in (True, False):
            nombre = f"semilla{semilla}_{'limpio' if entrenado_limpio else 'tal_cual'}"
            ruta = CACHE / f"validation_{nombre}.json"
            if ruta.exists():
                continue
            textos = [
                limpiar(fila["headline"]) if entrenado_limpio else fila["headline"]
                for fila in train
            ]
            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
            inicio = time.perf_counter()
            tokenizador, modelo = afinar(textos, etiquetas_train, semilla)
            segundos = time.perf_counter() - inicio
            if entrenado_limpio:
                destino = MODELOS / f"semilla{semilla}"
                modelo.save_pretrained(destino)
                tokenizador.save_pretrained(destino)
            _escribir(
                ruta,
                {
                    **_condiciones(),
                    "semilla": semilla,
                    "entrenado_limpio": entrenado_limpio,
                    "segundos": round(segundos, 1),
                    "pico_mib": round(torch.cuda.max_memory_allocated() / 2**20)
                    if torch.cuda.is_available()
                    else None,
                    "entrada_tal_cual": probabilidades(tokenizador, modelo, titulares),
                    "entrada_limpia": probabilidades(tokenizador, modelo, limpios),
                },
            )
            print(f"  {nombre}: {segundos:.0f} s", flush=True)
            del tokenizador, modelo
            _liberar()

    clickbait = sum(etiquetas) / len(etiquetas)
    print(
        f"\n== TA1C validation: {len(etiquetas)} tuits, {clickbait:.1%} clickbait; "
        f"votar «clickbait» siempre da F1 {2 * clickbait / (1 + clickbait):.3f}"
    )
    lineal = [linear.predict(titular).unwrap()["probability"] for titular in titulares]
    print(
        _linea(
            f"el lineal de producción (umbral {UMBRAL_LINEAL})",
            medida(etiquetas, lineal, UMBRAL_LINEAL),
        )
    )
    print("\n  semilla · entrenado · entrada")
    produccion = {}
    for semilla in SEMILLAS:
        for entrenado_limpio in (True, False):
            nombre = f"semilla{semilla}_{'limpio' if entrenado_limpio else 'tal_cual'}"
            guardado = _leer(CACHE / f"validation_{nombre}.json")
            for entrada in ("entrada_tal_cual", "entrada_limpia"):
                resultado = medida(etiquetas, guardado[entrada])
                etiqueta = f"{semilla} · {'limpio' if entrenado_limpio else 'tal cual'} · {entrada.removeprefix('entrada_').replace('_', ' ')}"
                print(_linea(etiqueta, resultado))
                if entrenado_limpio and entrada == "entrada_tal_cual":
                    produccion[semilla] = resultado["f1"]
    elegida = max(SEMILLAS, key=lambda semilla: (produccion[semilla], -semilla))
    print(
        f"\n== ELEGIDA: la semilla {elegida} (F1 {produccion[elegida]:.3f} entrenada limpia, "
        "con la entrada tal cual, como producción)"
    )
    _escribir(
        CACHE / "validation.json",
        {"semilla": elegida, "f1_produccion": produccion},
    )


def medios_fuera() -> None:
    elegida = _leer(CACHE / "validation.json")
    if elegida is None:
        raise SystemExit("Antes, `validation`: elige la semilla.")
    semilla = elegida["semilla"]
    conjunto = ta1c("train") + ta1c("validation")
    medios = {fila["medio"] for fila in conjunto}
    repartidos = [medio for pliegue in PLIEGUES for medio in pliegue]
    if sorted(repartidos) != sorted(medios):
        raise SystemExit(f"Los pliegues no cubren los medios: {sorted(medios)}")
    datos = cargar_datos()

    etiquetas, beto, lineal = [], [], []
    for numero, fuera in enumerate(PLIEGUES, 1):
        ruta = CACHE / f"medios_fuera_{numero}.json"
        guardado = _leer(ruta)
        dentro = [fila for fila in conjunto if fila["medio"] not in fuera]
        de_fuera = [fila for fila in conjunto if fila["medio"] in fuera]
        if guardado is None:
            inicio = time.perf_counter()
            tokenizador, modelo = afinar(
                [limpiar(fila["headline"]) for fila in dentro],
                [fila["label"] for fila in dentro],
                semilla,
            )
            de_beto = probabilidades(
                tokenizador, modelo, [fila["headline"] for fila in de_fuera]
            )
            del tokenizador, modelo
            _liberar()
            # El lineal, como en producción: bilingüe, con la parte de TA1C de
            # este pliegue, y su umbral.
            vectorizador, regresion = entrenar(
                FEATURIZACION,
                datos["chak_train"]
                + datos["webis_train"]
                + [(fila["headline"], fila["label"]) for fila in dentro],
            )
            probabilidades_lineal = regresion.predict_proba(
                vectorizador.transform([fila["headline"] for fila in de_fuera])
            )[:, 1].tolist()
            guardado = {
                **_condiciones(),
                "semilla": semilla,
                "fuera": list(fuera),
                "segundos": round(time.perf_counter() - inicio, 1),
                "etiquetas": [fila["label"] for fila in de_fuera],
                "beto": de_beto,
                "lineal": probabilidades_lineal,
            }
            _escribir(ruta, guardado)
            print(f"  pliegue {numero}: {guardado['segundos']:.0f} s", flush=True)
        etiquetas += guardado["etiquetas"]
        beto += guardado["beto"]
        lineal += guardado["lineal"]
        f1_beto = medida(guardado["etiquetas"], guardado["beto"])["f1"]
        f1_lineal = medida(guardado["etiquetas"], guardado["lineal"], UMBRAL_LINEAL)[
            "f1"
        ]
        print(
            f"  pliegue {numero} ({len(guardado['etiquetas'])} tuits, fuera {', '.join(fuera)}): "
            f"BETO F1 {f1_beto:.3f} · lineal F1 {f1_lineal:.3f}"
        )

    de_beto = medida(etiquetas, beto)
    del_lineal = medida(etiquetas, lineal, UMBRAL_LINEAL)
    print(f"\n== medios fuera, los seis pliegues juntos ({len(etiquetas)} tuits)")
    print(_linea(f"BETO, semilla {semilla}, entrenado limpio", de_beto))
    print(_linea(f"el lineal (umbral {UMBRAL_LINEAL})", del_lineal))
    delta, bajo, alto = diferencia_con_intervalo(
        etiquetas, de_beto["votos"], del_lineal["votos"]
    )
    cumple = de_beto["f1"] > del_lineal["f1"]
    print(
        f"  F1 de BETO menos el del lineal: {delta:+.3f} [{bajo:+.3f}, {alto:+.3f}] "
        "(información: la regla no mira el ruido)"
    )
    print(f"  => (b) {'CUMPLE' if cumple else 'NO cumple'}: BETO por encima del lineal")
    _escribir(
        CACHE / "medios_fuera.json",
        {
            "semilla": semilla,
            "f1_beto": de_beto["f1"],
            "f1_lineal": del_lineal["f1"],
            "cumple": cumple,
        },
    )


async def _comprobar_paridad(
    ruta_modelo: str, titulares: list[str], probabilidades_aqui: list[float]
) -> None:
    """La etiqueta que da `dedicated.detect`, con el modelo guardado, es la de
    aquí: así lo medido es la señal, y las etiquetas no hay que configurarlas."""
    cliente = LocalNLPClient()
    for titular, probabilidad in zip(titulares, probabilidades_aqui, strict=True):
        resultado = await dedicated.detect(
            cliente, titular, ruta_modelo, dedicated.CLASIFICACION
        )
        if not resultado.has_content():
            raise SystemExit(f"`detect` falló: {resultado.error}")
        esperada = "clickbait" if probabilidad > 0.5 else "factual news"
        if resultado.data["label"] != esperada:
            raise SystemExit(
                f"PARIDAD ROTA: «{titular}» da {resultado.data['label']} en `detect` "
                f"y {esperada} aquí ({probabilidad:.4f})"
            )
    print(f"  paridad con `dedicated.detect`: {len(titulares)} titulares, iguales")


def test() -> None:
    """La elegida, UNA vez, en TA1C `test`, con las dos partes de la regla."""
    elegida = _leer(CACHE / "validation.json")
    fuera = _leer(CACHE / "medios_fuera.json")
    if elegida is None or fuera is None:
        raise SystemExit("Antes, `validation` y `medios-fuera`.")
    semilla = elegida["semilla"]
    ruta_modelo = MODELOS / f"semilla{semilla}"
    filas = ta1c("test")
    titulares = [fila["headline"] for fila in filas]
    etiquetas = [fila["label"] for fila in filas]

    ruta = CACHE / "test.json"
    guardado = _leer(ruta)
    if guardado is not None:
        if guardado["semilla"] != semilla:
            raise SystemExit(
                f"`test` ya se abrió el {guardado['fecha']} con la semilla {guardado['semilla']}: no se vuelve a abrir."
            )
        print(
            f"== `test` ya se abrió el {guardado['fecha']}: lo guardado, sin volver a ejecutar el modelo"
        )
    else:
        tokenizador = AutoTokenizer.from_pretrained(ruta_modelo)
        modelo = AutoModelForSequenceClassification.from_pretrained(ruta_modelo).to(
            _dispositivo()
        )
        guardado = {
            **_condiciones(),
            "semilla": semilla,
            "probabilidades": probabilidades(tokenizador, modelo, titulares),
        }
        _escribir(ruta, guardado)
        del tokenizador, modelo
        _liberar()
        asyncio.run(
            _comprobar_paridad(
                str(ruta_modelo),
                titulares[:MUESTRA_PARIDAD],
                guardado["probabilidades"][:MUESTRA_PARIDAD],
            )
        )

    clickbait = sum(etiquetas) / len(etiquetas)
    print(
        f"== TA1C test: {len(etiquetas)} tuits, {clickbait:.1%} clickbait; "
        f"votar «clickbait» siempre da F1 {2 * clickbait / (1 + clickbait):.3f}"
    )
    de_beto = medida(etiquetas, guardado["probabilidades"])
    lineal = [linear.predict(titular).unwrap()["probability"] for titular in titulares]
    del_lineal = medida(etiquetas, lineal, UMBRAL_LINEAL)
    print(
        _linea(f"BETO, semilla {semilla}, abierto el {guardado['fecha'][:16]}", de_beto)
    )
    print(_linea(f"el lineal de producción (umbral {UMBRAL_LINEAL})", del_lineal))
    if round(del_lineal["f1"], 3) != LISTON_TEST:
        print(
            f"  ⚠️ el lineal NO reproduce el {LISTON_TEST} de #231 ({del_lineal['f1']:.4f})"
        )
    delta, bajo, alto = diferencia_con_intervalo(
        etiquetas, de_beto["votos"], del_lineal["votos"]
    )
    print(
        f"  F1 de BETO menos el del lineal: {delta:+.3f} [{bajo:+.3f}, {alto:+.3f}] (información)"
    )
    cumple_a = de_beto["f1"] >= LISTON_TEST
    print(
        f"  (a) {'CUMPLE' if cumple_a else 'NO cumple'}: F1 {de_beto['f1']:.3f} frente al listón {LISTON_TEST}"
    )
    print(
        f"  (b) {'CUMPLE' if fuera['cumple'] else 'NO cumple'}: con medios fuera, "
        f"BETO {fuera['f1_beto']:.3f} frente al lineal {fuera['f1_lineal']:.3f}"
    )
    print(f"  => {'SE QUEDA' if cumple_a and fuera['cumple'] else 'NO se queda'}")


def tiempo() -> None:
    if torch.cuda.is_available():
        raise SystemExit(
            "La GPU está a la vista: lánzalo con CUDA_VISIBLE_DEVICES= para medir en CPU, como producción."
        )
    elegida = _leer(CACHE / "validation.json")
    if elegida is None:
        raise SystemExit("Antes, `validation`.")
    ruta_modelo = str(MODELOS / f"semilla{elegida['semilla']}")
    titulares = [fila["headline"] for fila in ta1c("validation")[:MUESTRA_TIEMPO]]
    with open("/proc/cpuinfo", encoding="utf-8") as fichero:
        procesador = next(
            linea.split(":", 1)[1].strip()
            for linea in fichero
            if linea.startswith("model name")
        )
    cliente = LocalNLPClient()
    inicio = time.perf_counter()
    pipe = cliente._get_pipeline(dedicated.CLASIFICACION, ruta_modelo)
    carga = time.perf_counter() - inicio
    for titular in titulares[:CALENTAMIENTO_TIEMPO]:
        pipe(titular)
    segundos = []
    for titular in titulares:
        inicio = time.perf_counter()
        pipe(titular)
        segundos.append(time.perf_counter() - inicio)
    segundos.sort()
    print(
        f"== CPU: {procesador}, {torch.get_num_threads()} hilos; {len(titulares)} titulares, uno a uno"
    )
    print(
        f"  carga {carga:.1f} s · por titular: mediana {statistics.median(segundos):.3f} s, "
        f"p95 {segundos[int(0.95 * len(segundos)) - 1]:.3f} s ({pipe.device})"
    )


def main() -> None:
    partes = {
        "memoria": memoria,
        "validation": validation,
        "medios-fuera": medios_fuera,
        "test": test,
        "tiempo": tiempo,
    }
    parte = sys.argv[1] if len(sys.argv) > 1 else ""
    if parte not in partes:
        raise SystemExit(
            f"Uso: python -m backend.evaluation.eval_dedicada_es [{' | '.join(partes)}]"
        )
    partes[parte]()


if __name__ == "__main__":
    main()
