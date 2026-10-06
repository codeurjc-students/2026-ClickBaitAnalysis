"""¿Debe el engaño pisar a la forma en el veredicto? (issue #124)

Hasta #124, `_overall` derivaba la etiqueta global con una jerarquía: si la
dimensión de engaño decía «sí», el veredicto era `deceptive` dijera lo que dijera
la forma. Desde #124 corre «veto si discrepa» (abajo), elegida con este guion; la
regla de antes queda escrita aquí, en `regla_antes_de_124`, para que la
comparación se pueda repetir. El
razonamiento —un titular sobrio cuyo cuerpo no cumple es clickbait aunque las
señales de forma no lo vean— era bueno. Lo que #92 midió después es que la única
señal de esa dimensión, la incoherencia, acierta el 12 % de las veces justo
donde decide sola. Esto mide lo que le pasa al VEREDICTO, no a la señal.

LAS TRES REGLAS, Y DÓNDE DIFIEREN

Sólo difieren cuando el engaño dice «sí» y la forma no lo apoya: dice «no» o sus
señales discrepan. En todo lo demás, las tres son la de antes de #124:

- la de antes de #124: `deceptive`;
- sin veto (opción 2 de #124): `ambiguous`. La discrepancia ENTRE dimensiones se
  declara igual que la que hay DENTRO de una;
- cascada (opción 4): el engaño sólo cuenta si la forma dice «sí»; si no, manda
  la forma (`factual` con la forma en «no», `ambiguous` con discrepancia).

LA REGLA, FIJADA ANTES DE MEDIR (comentario en #124, 4 oct 2026)

La de antes se queda sólo si `deceptive` acierta al menos la mitad de las veces
cuando la forma no lo apoya: precisión ≥ 0,50, el suelo que #92 fijó para una
señal que pisa a las demás. Si no llega, la elección entre las otras dos la hace
el autor con los datos de la sección 3.

CON EL CÓDIGO DE PRODUCCIÓN, NO CON LAS CACHÉS DE #92

Cada par pasa por `analyze()` del orquestador. Las similitudes que #92 guardó en
`var/` se calcularon con el cuerpo entero, y producción lo recorta a 1.000
caracteres antes de comparar (`IncoherenceDetector._lead`): reutilizarlas sería
medir un sistema que no es el que corre. El resultado de cada par se guarda en
`var/`, así que sólo la primera ejecución es lenta, y si se corta se retoma
donde se quedó. La caché lleva la huella de todo lo que decide el resultado
—el código y los datos de las señales, el orquestador, los modelos efectivos y,
desde #93, los umbrales efectivos—, para que una caché de otro sistema no se
cuele en silencio.

La etiqueta humana es la de clickbait de Webis (`truthMean`): no hay una de
engaño. Es la misma limitación que la de #92.

LO QUE SE AÑADIÓ AL VER LOS DATOS (4 oct 2026)

La regla dio por buena la de antes (59,6 % ≥ 0,50), pero la sección 2 enseñó que
ese número junta dos casos opuestos: con la forma en discrepancia, `deceptive`
acertó el 68,4 %; con las tres señales de forma en «no», el 13,3 %. De ahí sale
una cuarta regla que NO estaba en la fijada antes de medir, «veto si
discrepa»: el engaño desempata una forma dividida, pero no contradice a una
forma unánime, y entonces el veredicto es `ambiguous`. El destino es una
decisión de postura del autor, no de los datos —`factual` daría las mismas
cifras, porque ninguna de las dos cuenta como clickbait—: la discrepancia entre
dimensiones se enseña, no se resuelve.

Por elegirse viendo los datos, se valida como en #92 (sección 4): el criterio se
aplica por subgrupo en una mitad y se comprueba en la otra.

    NLP_BACKEND=local python -m backend.evaluation.eval_veredicto

Con un número detrás, prueba sólo los primeros pares y no toca la caché.
"""

import asyncio
import hashlib
import json
import random
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from sklearn.metrics import precision_recall_fscore_support

from backend.analysis.domain import (
    AnalyzeRequest,
    Dimension,
    DimensionVerdict,
    OverallVerdict,
)
from backend.analysis.orchestrator import _overall, analyze
from backend.evaluation.eval_ambiguedad import es_unanime
from backend.evaluation.eval_incoherencia import (
    MITAD_CALIBRACION,
    SEMILLA,
    SPLIT,
    cargar_pares,
)
from backend.integrations.nlp.factory import (
    get_incoherence_detector,
    get_invocacion,
    get_model_id,
    get_threshold,
)

_RAIZ = Path(__file__).resolve().parents[2]
CACHE = _RAIZ / "var" / f"veredicto_{SPLIT}.json"

# Lo que decide el resultado de un par. Si cambia cualquiera de estos ficheros,
# la caché deja de valer.
DECIDEN = (
    _RAIZ / "backend" / "integrations" / "nlp",
    _RAIZ / "backend" / "analysis" / "orchestrator.py",
    _RAIZ / "backend" / "analysis" / "domain.py",
)
SEÑALES_CON_MODELO = ("detect_clickbait", "analyze_sentiment")

# El suelo de la regla (#124), fijado antes de medir: el mismo de #92.
MIN_PRECISION = 0.50
# Cada cuántos pares se guarda lo hecho, para poder retomar.
CADA = 500
POSITIVOS = {OverallVerdict.DECEPTIVE, OverallVerdict.STYLISTIC_CLICKBAIT}

Regla = Callable[[list[DimensionVerdict]], OverallVerdict]


# ----------------------------------------------------------- las condiciones


def modelos() -> dict[str, str]:
    """Los modelos EFECTIVOS: los de la ficha, o los de la configuración si hay."""
    efectivos = {señal: get_model_id(señal) for señal in SEÑALES_CON_MODELO}
    # Desde #159, en la dedicada deciden también el modo y las etiquetas: el
    # mismo id como zero-shot es otra señal.
    efectivos["detect_clickbait"] = get_invocacion("detect_clickbait").model_dump_json()
    efectivos["detect_clickbait_incoherence"] = get_incoherence_detector().model_id
    return efectivos


def umbrales() -> dict[str, float]:
    """Los umbrales EFECTIVOS (#93): los de los detectores, o los configurados.

    Van en la huella porque deciden el voto de dos señales: sin ellos, una
    ejecución con otro umbral reutilizaría la caché del anterior sin avisar.
    """
    return {
        "detect_clickbait_lexical": get_threshold("detect_clickbait_lexical"),
        "detect_clickbait_incoherence": get_incoherence_detector().threshold,
    }


def huella() -> str:
    """Un resumen de todo lo que decide el resultado de un par."""
    resumen = hashlib.sha256()
    ficheros = []
    for ruta in DECIDEN:
        if ruta.is_dir():
            ficheros += [
                fichero
                for fichero in ruta.rglob("*")
                if fichero.is_file() and "__pycache__" not in fichero.parts
            ]
        else:
            ficheros.append(ruta)
    for fichero in sorted(ficheros):
        resumen.update(str(fichero.relative_to(_RAIZ)).encode())
        resumen.update(fichero.read_bytes())
    resumen.update(json.dumps(modelos(), sort_keys=True).encode())
    resumen.update(json.dumps(umbrales(), sort_keys=True).encode())
    return resumen.hexdigest()[:12]


def _git(*argumentos: str) -> str:
    salida = subprocess.run(
        ["git", *argumentos], cwd=_RAIZ, capture_output=True, text=True, check=False
    )
    return salida.stdout.strip()


def condiciones(pares: list[dict]) -> None:
    sin_commitear = _git(
        "status",
        "--porcelain",
        "--",
        *(str(ruta.relative_to(_RAIZ)) for ruta in DECIDEN),
    )
    print("== condiciones")
    print(f"  fecha: {datetime.now(UTC).astimezone().isoformat(timespec='seconds')}")
    print(
        f"  commit: {_git('rev-parse', '--short', 'HEAD')}"
        + (
            "  ⚠️ CON CAMBIOS SIN COMMITEAR en lo que decide el resultado"
            if sin_commitear
            else ""
        )
    )
    print(f"  huella: {huella()}")
    for señal, modelo in modelos().items():
        print(f"  {señal}: {modelo}")
    print(
        "  umbrales: "
        + " · ".join(f"{señal} {umbral:g}" for señal, umbral in umbrales().items())
    )
    print(f"  pares titular–cuerpo de Webis-17 ({SPLIT}): {len(pares)}")
    # Producción corre en CPU; aquí, si hay GPU, las librerías la usan. Las
    # diferencias de coma flotante sólo moverían un caso en el filo del corte.
    import torch

    print(f"  torch {torch.__version__} · GPU disponible: {torch.cuda.is_available()}")


# --------------------------------------------------- pasar cada par por analyze()


async def _analizar(par: dict) -> dict:
    """Lo que el veredicto necesita de un par, sacado de `analyze()`."""
    fila = {"id": par["id"], "label": par["label"], "unanime": es_unanime(par)}
    try:
        peticion = AnalyzeRequest(headline=par["headline"], content=par["content"])
    except ValidationError:
        # Un titular en blanco: la API lo rechazaría con un 422.
        return {**fila, "rechazado": True}
    respuesta = await analyze(peticion)
    incoherencia = next(
        senal
        for senal in respuesta.signals
        if senal.name == "detect_clickbait_incoherence"
    )
    return {
        **fila,
        "senales": {
            senal.name: {"estado": senal.status.value, "voto": senal.is_clickbait}
            for senal in respuesta.signals
        },
        "similitud": (incoherencia.data or {}).get("similarity"),
        "dimensiones": [
            dimension.model_dump(mode="json") for dimension in respuesta.dimensions
        ],
        "veredicto": respuesta.verdict.value,
    }


def _retomar(clave: str, ids: list[str]) -> list[dict]:
    """Lo ya hecho con este mismo sistema y estos mismos pares, o nada."""
    if not CACHE.exists():
        return []
    guardado = json.loads(CACHE.read_text(encoding="utf-8"))
    if guardado["huella"] != clave or guardado["ids"] != ids:
        print("  (la caché es de otro sistema o de otros pares: se empieza de cero)")
        return []
    return guardado["filas"]


def _guardar(clave: str, ids: list[str], filas: list[dict]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps({"huella": clave, "ids": ids, "filas": filas}), encoding="utf-8"
    )


async def evaluar(pares: list[dict], *, con_cache: bool = True) -> list[dict]:
    """Pasa cada par por `analyze()`, guardando cada `CADA` pares."""
    clave = huella()
    ids = [par["id"] for par in pares]
    filas = _retomar(clave, ids) if con_cache else []
    if len(filas) == len(pares):
        print("  (reusando los resultados guardados)")
        return filas
    if filas:
        print(f"  (retomando en el par {len(filas)})")

    inicio = time.perf_counter()
    hechos_al_empezar = len(filas)
    for indice in range(len(filas), len(pares)):
        filas.append(await _analizar(pares[indice]))
        hechos = indice + 1
        if hechos % CADA == 0 or hechos == len(pares):
            if con_cache:
                _guardar(clave, ids, filas)
            ritmo = (time.perf_counter() - inicio) / (hechos - hechos_al_empezar)
            quedan = ritmo * (len(pares) - hechos) / 60
            print(
                f"  {hechos}/{len(pares)} · {ritmo:.3f} s por par · quedan ~{quedan:.0f} min",
                flush=True,
            )
    return filas


# ------------------------------------------------------------------ las reglas


def _forma_sin_apoyo(dimensiones: list[DimensionVerdict]) -> DimensionVerdict | None:
    """La dimensión de forma, si este par es de los que separan las reglas.

    Son los pares donde el engaño dice «sí» y la forma no lo apoya: dice «no» o
    sus señales discrepan. Una forma que no votó no cuenta como falta de apoyo:
    no hay nada con lo que discrepar.
    """
    por_dimension = {veredicto.dimension: veredicto for veredicto in dimensiones}
    engano = por_dimension.get(Dimension.DECEPTION)
    forma = por_dimension.get(Dimension.FORM)
    if engano is None or not engano.is_clickbait or forma is None or forma.is_clickbait:
        return None
    return forma


def regla_antes_de_124(dimensiones: list[DimensionVerdict]) -> OverallVerdict:
    """La jerarquía que tenía `_overall` hasta #124, escrita aquí.

    Producción la cambió por lo que midió este guion, así que importarla ya no
    reproduciría la comparación: se copia tal como era (`orchestrator.py` en
    `66891c5`), y `comprobar` vigila que la de producción sea «veto si discrepa».
    """
    if not dimensiones:
        return OverallVerdict.NO_DATA
    por_dimension = {veredicto.dimension: veredicto for veredicto in dimensiones}
    engano = por_dimension.get(Dimension.DECEPTION)
    forma = por_dimension.get(Dimension.FORM)
    if engano is not None and engano.is_clickbait:
        return OverallVerdict.DECEPTIVE
    if forma is not None and forma.is_clickbait:
        return OverallVerdict.STYLISTIC_CLICKBAIT
    if any(veredicto.is_clickbait is None for veredicto in dimensiones):
        return OverallVerdict.AMBIGUOUS
    return OverallVerdict.FACTUAL


def regla_sin_veto(dimensiones: list[DimensionVerdict]) -> OverallVerdict:
    if _forma_sin_apoyo(dimensiones) is not None:
        return OverallVerdict.AMBIGUOUS
    return regla_antes_de_124(dimensiones)


def regla_cascada(dimensiones: list[DimensionVerdict]) -> OverallVerdict:
    if _forma_sin_apoyo(dimensiones) is not None:
        sin_engano = [
            veredicto
            for veredicto in dimensiones
            if veredicto.dimension != Dimension.DECEPTION
        ]
        return regla_antes_de_124(sin_engano)
    return regla_antes_de_124(dimensiones)


def _subgrupo(forma: DimensionVerdict) -> str:
    """En cuál de los dos casos de la sección 2 cae una forma sin apoyo."""
    return "forma «no»" if forma.is_clickbait is False else "forma en discrepancia"


SUBGRUPOS = ("forma «no»", "forma en discrepancia")


def _regla_con_veto_en(subgrupos_con_veto: set[str]) -> Regla:
    """La jerarquía de antes de #124, sin el veto donde no se conserva."""

    def regla(dimensiones: list[DimensionVerdict]) -> OverallVerdict:
        forma = _forma_sin_apoyo(dimensiones)
        if forma is not None and _subgrupo(forma) not in subgrupos_con_veto:
            return OverallVerdict.AMBIGUOUS
        return regla_antes_de_124(dimensiones)

    return regla


def regla_veto_si_discrepa(dimensiones: list[DimensionVerdict]) -> OverallVerdict:
    """Elegida AL VER la sección 2: el engaño sólo pisa a una forma dividida."""
    forma = _forma_sin_apoyo(dimensiones)
    if forma is not None and forma.is_clickbait is False:
        return OverallVerdict.AMBIGUOUS
    return regla_antes_de_124(dimensiones)


REGLAS: dict[str, Regla] = {
    "antes de #124": regla_antes_de_124,
    "sin veto": regla_sin_veto,
    "cascada": regla_cascada,
    "veto si discrepa": regla_veto_si_discrepa,
}


# ---------------------------------------------------------------- las medidas


def _dimensiones(fila: dict) -> list[DimensionVerdict]:
    return [
        DimensionVerdict.model_validate(guardada) for guardada in fila["dimensiones"]
    ]


def _pct(parte: int, total: int) -> str:
    return f"{100 * parte / total:.1f} %" if total else "—"


def _prf(etiquetas: list[int], predichas: list[int]) -> str:
    precision, recall, f1, _ = precision_recall_fscore_support(
        etiquetas, predichas, average="binary", zero_division=0
    )
    return f"P {precision:.3f} · R {recall:.3f} · F1 {f1:.3f}"


def comprobar(filas: list[dict]) -> None:
    """Cada señal por separado, para cotejar con #124 y #92 antes de leer nada."""
    print(f"\n{'=' * 78}\n1 · COMPROBACIÓN: CADA SEÑAL POR SEPARADO\n{'=' * 78}")
    for señal in (
        "detect_clickbait",
        "detect_clickbait_lexical",
        "detect_clickbait_linear",
        "detect_clickbait_incoherence",
    ):
        estados = Counter(fila["senales"][señal]["estado"] for fila in filas)
        votaron = [fila for fila in filas if fila["senales"][señal]["voto"] is not None]
        etiquetas = [fila["label"] for fila in votaron]
        votos = [int(fila["senales"][señal]["voto"]) for fila in votaron]
        print(f"  {señal:30} {_prf(etiquetas, votos)} · {dict(estados)}")
    print(
        "  Para cotejar: #124 da F1 0,758 a la dedicada en este split, y #92, P 0,649"
    )
    print("  a la incoherencia en su mitad de test (aquí es el corpus entero).")

    # Dos comprobaciones. La primera, que reaplicar `_overall` sobre lo guardado
    # da lo mismo que dio `analyze()`: comparar reglas sobre la caché es fiel.
    # La segunda, desde #124, que lo que corre en producción es lo que se eligió.
    distintos = sum(
        1 for fila in filas if _overall(_dimensiones(fila)).value != fila["veredicto"]
    )
    print(
        f"\n  `_overall` frente al veredicto que dio `analyze()`: {distintos} distintos (tiene que ser 0)"
    )
    distintos = sum(
        1
        for fila in filas
        if _overall(_dimensiones(fila)) != regla_veto_si_discrepa(_dimensiones(fila))
    )
    print(
        f"  `_overall` frente a «veto si discrepa»: {distintos} distintos (desde #124, tiene que ser 0)"
    )


def aplicar_regla(filas: list[dict]) -> None:
    """La regla de #124: ¿acierta `deceptive` donde la forma no lo apoya?"""
    print(
        f"\n{'=' * 78}\n2 · LA REGLA: PRECISIÓN DE `deceptive` DONDE LA FORMA NO LO APOYA\n{'=' * 78}"
    )
    en_juego = [(fila, _forma_sin_apoyo(_dimensiones(fila))) for fila in filas]
    en_juego = [(fila, forma) for fila, forma in en_juego if forma is not None]
    grupos = {
        "forma «no»": [fila for fila, forma in en_juego if forma.is_clickbait is False],
        "forma en discrepancia": [
            fila for fila, forma in en_juego if forma.is_clickbait is None
        ],
        "las dos": [fila for fila, _ in en_juego],
    }
    for nombre, grupo in grupos.items():
        aciertos = sum(fila["label"] for fila in grupo)
        print(
            f"  {nombre:22} {len(grupo):>6} pares · clickbait según los anotadores: {aciertos:>5} · precisión {_pct(aciertos, len(grupo))}"
        )
    todos = grupos["las dos"]
    print(f"\n  en juego: {_pct(len(todos), len(filas))} de los pares")
    if not todos:
        print("  -> ningún par en juego: la regla no se puede aplicar")
        return
    precision = sum(fila["label"] for fila in todos) / len(todos)
    if precision >= MIN_PRECISION:
        print(
            f"  -> {precision:.3f} ≥ {MIN_PRECISION}: SE QUEDA la regla de antes de #124"
        )
    else:
        print(
            f"  -> {precision:.3f} < {MIN_PRECISION}: CAE la regla de antes de #124; la elección es del autor (sección 3)"
        )


def comparar(filas: list[dict]) -> None:
    """Lo que cambia con cada regla, para elegir entre las alternativas."""
    print(f"\n{'=' * 78}\n3 · PARA ELEGIR: LO QUE CAMBIA CON CADA REGLA\n{'=' * 78}")
    veredictos = {
        nombre: [regla(_dimensiones(fila)) for fila in filas]
        for nombre, regla in REGLAS.items()
    }
    etiquetas = [fila["label"] for fila in filas]
    unanimes = [indice for indice, fila in enumerate(filas) if fila["unanime"]]

    print("\n  Cuántos titulares caen en cada etiqueta:")
    print(
        f"  {'':16}" + "".join(f"{etiqueta.value:>23}" for etiqueta in OverallVerdict)
    )
    for nombre, lista in veredictos.items():
        cuenta = Counter(lista)
        print(
            f"  {nombre:16}"
            + "".join(
                f"{cuenta[etiqueta]:>14} ({_pct(cuenta[etiqueta], len(lista)):>6})"
                for etiqueta in OverallVerdict
            )
        )

    print(
        "\n  «Es clickbait» (`deceptive` o `stylistic_clickbait`) frente a la etiqueta humana:"
    )
    for nombre, lista in veredictos.items():
        predichas = [int(veredicto in POSITIVOS) for veredicto in lista]
        en_unanimes = _prf(
            [etiquetas[indice] for indice in unanimes],
            [predichas[indice] for indice in unanimes],
        )
        print(
            f"  {nombre:16} todo: {_prf(etiquetas, predichas)}   ·   unánimes ({len(unanimes)}): {en_unanimes}"
        )

    print("\n  Dentro de cada etiqueta, cuántos son clickbait según los anotadores:")
    for nombre, lista in veredictos.items():
        partes = []
        for etiqueta in (
            OverallVerdict.DECEPTIVE,
            OverallVerdict.AMBIGUOUS,
            OverallVerdict.FACTUAL,
        ):
            dentro = [
                etiquetas[indice]
                for indice, veredicto in enumerate(lista)
                if veredicto == etiqueta
            ]
            partes.append(f"{etiqueta.value} {_pct(sum(dentro), len(dentro))}")
        print(f"  {nombre:16} " + " · ".join(partes))

    print("\n  Lo que cambia respecto a la regla de antes de #124:")
    for nombre in ("sin veto", "cascada", "veto si discrepa"):
        cambios = Counter(
            (veredictos["antes de #124"][indice].value, veredicto.value)
            for indice, veredicto in enumerate(veredictos[nombre])
            if veredicto != veredictos["antes de #124"][indice]
        )
        if not cambios:
            print(f"  {nombre:16} (ninguno)")
        for (antes, despues), cuantos in sorted(cambios.items()):
            clickbait = sum(
                etiquetas[indice]
                for indice, veredicto in enumerate(veredictos[nombre])
                if veredictos["antes de #124"][indice].value == antes
                and veredicto.value == despues
            )
            print(
                f"  {nombre:16} {antes} → {despues}: {cuantos} pares, {_pct(clickbait, cuantos)} clickbait según los anotadores"
            )


def _etiquetas_del_subgrupo(
    filas: list[dict], indices: list[int], subgrupo: str
) -> list[int]:
    """La etiqueta humana de los pares de una mitad que caen en un subgrupo."""
    etiquetas = []
    for indice in indices:
        forma = _forma_sin_apoyo(_dimensiones(filas[indice]))
        if forma is not None and _subgrupo(forma) == subgrupo:
            etiquetas.append(filas[indice]["label"])
    return etiquetas


def validar_en_mitades(filas: list[dict]) -> None:
    """La regla elegida al ver los datos, elegida en una mitad y medida en la otra.

    El mismo reparto que #92, con su semilla y su proporción. En la mitad de
    elección se aplica el criterio de la sección 2 por subgrupo —el veto se
    queda donde `deceptive` acierta al menos `MIN_PRECISION`—; en la de
    comprobación se mira si cada subgrupo cae del mismo lado del corte, y si la
    regla que sale mejora a la de antes sobre datos que no la eligieron.
    """
    print(
        f"\n{'=' * 78}\n4 · LA REGLA ELEGIDA AL VER LOS DATOS, VALIDADA EN DOS MITADES\n{'=' * 78}"
    )
    indices = list(range(len(filas)))
    random.Random(SEMILLA).shuffle(indices)
    corte = int(len(indices) * MITAD_CALIBRACION)
    eleccion, comprobacion = indices[:corte], indices[corte:]
    print(
        f"  elección: {len(eleccion)} pares · comprobación: {len(comprobacion)} (el reparto de #92)"
    )

    con_veto = set()
    print(
        f"\n  {'precisión de `deceptive`':24} {'en la elección':>26} {'en la comprobación':>24}"
    )
    for subgrupo in SUBGRUPOS:
        en_eleccion = _etiquetas_del_subgrupo(filas, eleccion, subgrupo)
        en_comprobacion = _etiquetas_del_subgrupo(filas, comprobacion, subgrupo)
        if not en_eleccion or not en_comprobacion:
            print(f"  {subgrupo:24} sin pares en alguna mitad")
            continue
        precision_eleccion = sum(en_eleccion) / len(en_eleccion)
        precision_comprobacion = sum(en_comprobacion) / len(en_comprobacion)
        if precision_eleccion >= MIN_PRECISION:
            con_veto.add(subgrupo)
        mismo_lado = (precision_eleccion >= MIN_PRECISION) == (
            precision_comprobacion >= MIN_PRECISION
        )
        decision = "→ veto" if subgrupo in con_veto else "→ sin veto"
        print(
            f"  {subgrupo:24} {_pct(sum(en_eleccion), len(en_eleccion)):>8} de {len(en_eleccion):>4} {decision:>11}"
            f" {_pct(sum(en_comprobacion), len(en_comprobacion)):>12} de {len(en_comprobacion):>4}"
            f"  {'mismo lado del corte' if mismo_lado else 'CAMBIA DE LADO'}"
        )

    elegida = _regla_con_veto_en(con_veto)
    coincide = con_veto == {"forma en discrepancia"}
    print(
        f"\n  regla elegida en la primera mitad: veto en {sorted(con_veto) or 'ninguno'}"
        + (" — es «veto si discrepa»" if coincide else " — NO es «veto si discrepa»")
    )

    etiquetas = [filas[indice]["label"] for indice in comprobacion]
    unanimes = [indice for indice in comprobacion if filas[indice]["unanime"]]
    print(
        "\n  En la mitad de comprobación, «es clickbait» frente a la etiqueta humana:"
    )
    for nombre, regla in (("antes de #124", regla_antes_de_124), ("elegida", elegida)):
        predichas = [
            int(regla(_dimensiones(filas[indice])) in POSITIVOS)
            for indice in comprobacion
        ]
        predichas_unanimes = [
            int(regla(_dimensiones(filas[indice])) in POSITIVOS) for indice in unanimes
        ]
        en_unanimes = _prf(
            [filas[indice]["label"] for indice in unanimes], predichas_unanimes
        )
        print(
            f"  {nombre:16} todo: {_prf(etiquetas, predichas)}   ·   unánimes ({len(unanimes)}): {en_unanimes}"
        )


def main() -> None:
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else None
    pares = cargar_pares()[:limite]
    condiciones(pares)
    if limite:
        print(f"  PRUEBA con los primeros {limite}: no se lee ni se escribe la caché")
    filas = asyncio.run(evaluar(pares, con_cache=limite is None))
    validas = [fila for fila in filas if not fila.get("rechazado")]
    print(f"  rechazados por la API (titular en blanco): {len(filas) - len(validas)}")
    comprobar(validas)
    aplicar_regla(validas)
    comparar(validas)
    validar_en_mitades(validas)


if __name__ == "__main__":
    main()
