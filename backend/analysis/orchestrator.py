"""Orquestación del análisis: lanza las señales y agrega su resultado.

Lanza las señales de clickbait a la vez, envuelve cada una en el formato
uniforme de ``domain`` y agrega el resultado. Tres invariantes lo gobiernan:

1. **Una señal vota si —y solo si— su ``is_clickbait`` no es None.** Ahí caen
   sin caso especial las que fallaron y el tono, que por naturaleza no emite
   veredicto de clickbait. Entre #109 y #115 hubo un tercer caso —una señal
   excluida por medirse peor que las demás— y el mismo ``None`` bastó para
   expresarlo sin tocar la agregación: la palanca ya estaba puesta.
2. **Una dimensión aparece si alguna de sus señales votó.** Si las que votaron
   discrepan, no se promedia ni se resuelve por mayoría: se declara ``None``.
3. **El veredicto global sale de las dimensiones con jerarquía** —el engaño pesa
   más que la forma—, nunca de contar señales.

Por qué no vale la mayoría: un titular sobrio cuyo cuerpo no cumple lo prometido
tiene tres señales diciendo «no» y una diciendo «sí», y la correcta es la cuarta.

El aislamiento de fallos es el punto delicado: una señal caída no puede tumbar
las otras cuatro (~1 de cada 5 llamadas a HuggingFace da timeout, medido en la
Épica 4). Por eso se usa ``asyncio.gather(..., return_exceptions=True)``, que en
vez de propagar la primera excepción la DEVUELVE dentro de la lista de
resultados, en la posición que le toca. Cada excepción se traduce entonces a una
señal en estado ``error`` y la respuesta sigue siendo un 200 con lo que sí se
pudo calcular.

Vive fuera de ``api/`` porque **no depende de que haya HTTP**: es la lógica que
define qué significa el resultado, y las dos fachadas —REST y MCP— la comparten.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from backend.analysis.domain import (
    AnalyzeRequest,
    AnalyzeResponse,
    Dimension,
    DimensionVerdict,
    OverallVerdict,
    SignalResult,
    SignalStatus,
    SignalType,
)
from backend.core.models import ToolResult
from backend.integrations.nlp import dedicated, lexical, linear
from backend.integrations.nlp.factory import get_nlp_backend
from backend.integrations.nlp.incoherence import IncoherenceDetector
from backend.integrations.nlp.model_cards import cards_by_signal

log = structlog.get_logger()

# Instancias únicas: LocalNLPClient cachea los pipelines por instancia y el
# detector carga el modelo de forma perezosa, así que crearlos por petición
# tiraría la caché y recargaría el modelo cada vez. Como contrapartida, el
# backend queda fijado al importar: cambiarlo exige reiniciar, igual que en la
# tool MCP (que lo fija en register()).
#
# Y es lo que obliga a que precalentar() viva aquí: hay que calentar ESTAS dos
# instancias, no unas equivalentes, o el coste se paga dos veces.
_api = get_nlp_backend()
_detector = IncoherenceDetector()

# Índice de fichas por nombre de tool. Es lo que permite no cablear aquí la
# dimensión ni el tipo de cada señal: se leen de MODEL_CARDS (R3.9). Un desajuste
# entre esta clave y el nombre real de la tool lo detecta antes de llegar aquí
# test_model_cards_signals_match_registered_tools.
_CARDS = cards_by_signal()

# El id sale de la ficha (#116). Antes estaba cableado aquí y otra vez en
# integrations/nlp/tool.py, así que cambiar el modelo en un sitio dejaba las dos
# fachadas —REST y MCP— respondiendo con modelos distintos al mismo titular, y
# sin que nada fallara: los dos caminos seguían devolviendo una etiqueta válida.
#
# Sólo queda el del tono: la señal de clickbait pasó a `integrations/nlp/dedicated`
# en #115, que es donde viven ya sus hermanas —léxico, lineal, incoherencia— y
# donde el id y el mapeo de etiquetas tienen un único sitio.
_SENTIMENT_MODEL = _CARDS["analyze_sentiment"]["model_id"]


@dataclass(frozen=True)
class _Signal:
    """Cómo se ejecuta una señal y cómo se lee su veredicto.

    Declararlas en una tabla en vez de con cinco bloques casi idénticos deja el
    bucle de ejecución con una sola forma. Añadir una sexta señal es añadir una
    entrada a ``_SIGNALS`` y su ficha en MODEL_CARDS.

    ``@dataclass`` lee las anotaciones de campo y genera ``__init__``,
    ``__repr__`` y ``__eq__``, que es lo que ahorra escribir el constructor a
    mano. ``frozen=True`` añade inmutabilidad: asignar a un campo después de
    construir la instancia lanza ``FrozenInstanceError`` (y como efecto
    secundario genera ``__hash__``, así que son hashables).

    Se congela porque ``_SIGNALS`` es una tabla de constantes, leída al importar
    y compartida por todas las peticiones: sin ``frozen`` nada impediría que un
    handler hiciera ``spec.needs_content = True`` y mutara el comportamiento
    global. Ojo, la inmutabilidad es SUPERFICIAL —impide reasignar el campo, no
    mutar un objeto mutable guardado dentro—, pero aquí todos son str, bool o
    funciones, así que es efectiva del todo.

    TODO(futuro): si hace falta activar/desactivar señales por configuración,
    esta tabla es el punto de extensión — pasaría de constante a construirse
    desde settings.
    """

    name: str  # nombre EXACTO de la tool MCP; es la clave en _CARDS
    run: Callable[[str, str | None], Awaitable[ToolResult]]
    verdict: Callable[[dict[str, Any]], bool | None]
    needs_content: bool = False


# El extractor `verdict` existe porque cada tool expresa su conclusión a su
# manera (label / is_clickbait / incoherent), y ese paso interpretativo —"una
# similitud por debajo del umbral la leemos como clickbait"— se prefiere visible
# aquí antes que uniformando el retorno de las tools, que es contrato público
# leído por el LLM (validado en el spike #82).
_SIGNALS: tuple[_Signal, ...] = (
    _Signal(
        name="detect_clickbait",
        run=lambda h, c: dedicated.detect(_api, h),
        # VUELVE A VOTAR (#115), después de que #109 se lo quitara. No es una
        # marcha atrás: aquel silencio se declaró condicional en la ficha —
        # «placeholder pendiente de #115»— y esto es la condición cumpliéndose.
        #
        # Lo que #109 silenció fue un modelo elegido POR ELIMINACIÓN en E3-02,
        # que acertaba el 63,7 %. Su problema no era el error sino cómo se
        # propagaba: al discrepar en solitario dejaba la dimensión en None
        # (invariante 2), y así el 37 % de los titulares salía AMBIGUO con el
        # 78 % de esa ambigüedad siendo un error suyo.
        #
        # El sustituto cambia esos dos números a 15 % y 20 %. O sea que cuatro
        # de cada cinco ambigüedades pasan a ser discrepancia legítima, y
        # AMBIGUO recupera el significado que la tesis le atribuye. Ése es el
        # criterio, y no el acierto: «ambiguo» debe querer decir que dos señales
        # fiables no coinciden, no que alguna se equivocó.
        #
        # La etiqueta la normaliza `dedicated`, no esta tabla: el veredicto se
        # lee igual que antes aunque el modelo de debajo hable otro idioma.
        verdict=lambda d: d["label"] == "clickbait",
    ),
    _Signal(
        name="detect_clickbait_lexical",
        # Síncrona y de milisegundos: va a un hilo solo para que el bucle trate a
        # todas igual. El coste del hilo es despreciable frente a la uniformidad.
        run=lambda h, c: asyncio.to_thread(lexical.detect, h),
        verdict=lambda d: d["is_clickbait"],
    ),
    _Signal(
        name="detect_clickbait_linear",
        run=lambda h, c: asyncio.to_thread(linear.predict, h),
        verdict=lambda d: d["is_clickbait"],
    ),
    _Signal(
        name="detect_clickbait_incoherence",
        run=lambda h, c: _detector.detect(h, c),
        verdict=lambda d: d["incoherent"],
        needs_content=True,
    ),
    _Signal(
        name="analyze_sentiment",
        run=lambda h, c: _api.classify(h, _SENTIMENT_MODEL),
        # El tono se muestra como una señal más pero NO vota: alejarse de la
        # objetividad no es hacer clickbait, y cuánto pesa eso lo juzga quien
        # lee. Devolver None aquí es toda la implementación de esa decisión.
        verdict=lambda d: None,
    ),
)


async def precalentar() -> dict[str, float]:
    """Carga y ejercita los modelos antes de la primera petición (#125).

    Vive aquí y no en la app REST porque ``LocalNLPClient`` cachea sus pipelines
    **por instancia**: hay que calentar exactamente los objetos ``_api`` y
    ``_detector`` que va a usar la petición. Calentar otros equivalentes pagaría
    el coste dos veces y dejaría la primera petición igual de lenta.

    EJERCITA, no sólo carga. Medido en #125, el desglose de los ~102 s en frío:

        imports de torch/transformers/sentence-transformers   53,5 s
        carga de los tres modelos                             33,0 s
        PRIMERA inferencia                                    15,5 s

    Esos últimos 15,5 s no los paga cargar el modelo, sólo hacerle pasar una
    entrada. Y son en su mayoría coste GLOBAL, no por modelo: la primera
    inferencia del dedicado tardó 9,78 s y la del sentimiento 0,01 s, porque
    para entonces torch ya había inicializado lo suyo.

    Respeta ``nlp_backend``: con ``remote`` las señales de titular van por HTTP a
    HuggingFace y cargar sus modelos en local sería trabajo tirado. La
    incoherencia corre siempre en local, así que se calienta siempre.

    Devuelve los tiempos por señal para poder registrarlos, en vez de imprimir
    desde aquí: quien llama decide si eso se loguea y cómo.
    """
    from backend.config.settings import settings

    tiempos: dict[str, float] = {}
    titular = "Precalentando el modelo"

    async def cronometrar(etiqueta: str, tarea) -> None:
        inicio = time.perf_counter()
        try:
            await tarea()
        except Exception as exc:
            # No se propaga: un modelo que no carga no debe impedir que la API
            # sirva `/tools` o `/history`. Se registra el fallo con un tiempo
            # negativo para que sea inconfundible en los logs.
            log.warning("preheat.failed", signal=etiqueta, error=str(exc))
            tiempos[etiqueta] = -1.0
            return
        tiempos[etiqueta] = time.perf_counter() - inicio

    if settings.nlp_backend == "local":
        await cronometrar("detect_clickbait", lambda: dedicated.detect(_api, titular))
        await cronometrar(
            "analyze_sentiment", lambda: _api.classify(titular, _SENTIMENT_MODEL)
        )

    await cronometrar(
        "detect_clickbait_incoherence",
        lambda: _detector.detect(titular, "Un cuerpo cualquiera para calentar."),
    )
    return tiempos


async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analiza un titular con todas las señales aplicables.

    Sin lógica propia a propósito: cada invariante vive en su helper y se puede
    probar por separado.
    """
    signals = await _run_signals(request.headline, request.content)
    dimensions = _aggregate(signals)
    return AnalyzeResponse(
        headline=request.headline,
        content=request.content,
        signals=signals,
        dimensions=dimensions,
        verdict=_overall(dimensions),
    )


async def _run_signals(headline: str, content: str | None) -> list[SignalResult]:
    """Ejecuta en paralelo las señales aplicables y envuelve cada resultado."""
    by_name: dict[str, SignalResult] = {}
    pending: list[_Signal] = []

    for spec in _SIGNALS:
        if spec.needs_content and not (content and content.strip()):
            by_name[spec.name] = _build(
                spec,
                SignalStatus.NOT_APPLICABLE,
                detail="Requiere el cuerpo o teaser de la noticia.",
            )
        else:
            pending.append(spec)

    outcomes = await asyncio.gather(
        *(_run_one(spec, headline, content) for spec in pending),
        return_exceptions=True,
    )

    # gather conserva el ORDEN DE ENTRADA, no el de finalización: aunque el
    # zero-shot tarde 3 s y el léxico 2 ms, cada resultado vuelve en la posición
    # de su spec. Por eso el zip es correcto.
    for spec, outcome in zip(pending, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            # BaseException y no Exception: asyncio.CancelledError hereda de la
            # primera desde Python 3.8 y gather también la deposita en la lista.
            by_name[spec.name] = _build(
                spec,
                SignalStatus.ERROR,
                # TODO(deuda): el texto de la excepción es útil para depurar
                # pero expone interioridad. Sanear antes de salir de desarrollo.
                detail=f"{type(outcome).__name__}: {outcome}",
            )
        else:
            by_name[spec.name] = outcome

    # Se emiten en el orden de _SIGNALS para que la interfaz pinte las tarjetas
    # siempre igual, con independencia de cuál acabó antes o cuál se saltó.
    return [by_name[spec.name] for spec in _SIGNALS]


async def _run_one(spec: _Signal, headline: str, content: str | None) -> SignalResult:
    """Ejecuta UNA señal.

    Sin ``try/except``, y es deliberado: hay dos formas de fallar y cada una se
    trata donde le toca. El fallo PREVISTO (timeout de HuggingFace, titular
    vacío) llega como ``ToolResult.fail`` con su mensaje legible y se mapea
    aquí. El IMPREVISTO —la corrutina revienta, o ``spec.verdict`` da KeyError
    porque una tool cambió de formato— sube al ``gather``, que lo aísla.
    """
    outcome = await spec.run(headline, content)
    if not outcome.has_content():
        return _build(
            spec,
            SignalStatus.ERROR,
            detail=outcome.error or "La señal no devolvió resultado.",
        )
    return _build(
        spec,
        SignalStatus.OK,
        is_clickbait=spec.verdict(outcome.data),
        data=outcome.data,
    )


def _build(
    spec: _Signal,
    status: SignalStatus,
    *,
    is_clickbait: bool | None = None,
    data: dict[str, Any] | None = None,
    detail: str | None = None,
) -> SignalResult:
    """Envuelve el resultado de una señal leyendo dimensión y tipo de su ficha.

    Único sitio donde se construye un SignalResult, así que la traducción ficha
    → respuesta está en un solo punto. El acceso a ``_CARDS`` puede dar KeyError
    si se añade una señal sin ficha: es intencionado, y el test de alineación lo
    detecta antes.
    """
    card = _CARDS[spec.name]
    return SignalResult(
        name=spec.name,
        status=status,
        dimension=Dimension(card["dimension"]),
        type=SignalType(card["type"]),
        is_clickbait=is_clickbait,
        data=data,
        detail=detail,
    )


def _aggregate(signals: list[SignalResult]) -> list[DimensionVerdict]:
    """Agrupa por dimensión las señales que votaron (invariantes 1 y 2)."""
    votes: dict[Dimension, list[SignalResult]] = {}
    for signal in signals:
        # `is None` y no `if not signal.is_clickbait`: False es un veredicto
        # VÁLIDO —"esta señal dice que no es clickbait"— y con la comprobación
        # por falsedad se perderían todos los votos negativos, dejando cualquier
        # titular factual en no_data. Este único filtro cubre a la vez las
        # señales que fallaron y las que no votan por naturaleza (el tono).
        if signal.is_clickbait is None:
            continue
        votes.setdefault(signal.dimension, []).append(signal)

    verdicts = []
    for dimension, voters in votes.items():
        # Conjunto de booleanos: solo puede ser {True}, {False} o {True, False}.
        # Un elemento significa acuerdo; dos, discrepancia.
        distinct = {v.is_clickbait for v in voters}
        verdicts.append(
            DimensionVerdict(
                dimension=dimension,
                # next(iter(...)) porque un set no es indexable. Discrepancia →
                # None: dos señales de forma en desacuerdo es información, no
                # ruido que haya que resolver por mayoría.
                is_clickbait=next(iter(distinct)) if len(distinct) == 1 else None,
                contributing=[v.name for v in voters],
            )
        )
    return verdicts


def _overall(dimensions: list[DimensionVerdict]) -> OverallVerdict:
    """Deriva la etiqueta única con jerarquía explícita (invariante 3).

    Cadena de ``if`` y no ``match``: aquí no hay un sujeto sobre el que
    despachar —cada rama evalúa una condición distinta sobre objetos
    distintos—, y sobre todo el ORDEN ES la jerarquía. Un ``switch`` comunica
    «alternativas paralelas, el orden da igual», justo lo contrario.
    """
    # Primero: con la lista vacía, el any() de abajo daría False y caería en
    # FACTUAL, declarando factual un titular que nadie pudo analizar.
    if not dimensions:
        return OverallVerdict.NO_DATA

    by_dimension = {d.dimension: d for d in dimensions}
    deception = by_dimension.get(Dimension.DECEPTION)
    form = by_dimension.get(Dimension.FORM)

    # El engaño manda: un titular que promete lo que el cuerpo no cumple es
    # clickbait aunque esté redactado con sobriedad.
    if deception is not None and deception.is_clickbait:
        return OverallVerdict.DECEPTIVE
    if form is not None and form.is_clickbait:
        return OverallVerdict.STYLISTIC_CLICKBAIT
    # Una detección positiva pesa más que una discrepancia: solo si nadie ha
    # detectado nada importa que alguna dimensión quedara sin resolver. La
    # discrepancia no se pierde, sigue visible en dimensions[].
    if any(d.is_clickbait is None for d in dimensions):
        return OverallVerdict.AMBIGUOUS
    return OverallVerdict.FACTUAL
