"""Tests de la orquestación de /analyze.

Ninguno toca la red ni carga modelos: se sustituyen las cuatro fuentes reales
(`_api`, `_detector`, `lexical.detect`, `linear.predict`) por dobles
controlables. Las lambdas de `_SIGNALS` resuelven `_api` y `_detector` como
globales del módulo EN CADA LLAMADA, así que monkeypatchear el módulo basta.
"""

import asyncio
import time
from typing import ClassVar

import pytest
from pydantic import ValidationError

from backend.analysis import orchestrator
from backend.analysis.domain import (
    AnalyzeRequest,
    Dimension,
    DimensionVerdict,
    OverallVerdict,
    SignalStatus,
)
from backend.analysis.orchestrator import (
    _SIGNALS,
    _aggregate,
    _build,
    _overall,
    _run_signals,
)
from backend.core.models import ToolResult
from backend.integrations.nlp import dedicated, lexical, linear
from backend.integrations.nlp.model_cards import cards_by_signal

_SPECS = {spec.name: spec for spec in _SIGNALS}


# ----- Dobles -----


class _FakeAPI:
    """Backend NLP sin red. `delay` sirve para medir la concurrencia.

    `classify` DESPACHA POR MODELO desde #115. Antes sólo lo usaba el tono, así
    que devolver siempre su etiqueta bastaba; ahora la señal de clickbait usa el
    mismo método, y un doble que ignorase el modelo le devolvería «neutral» a
    `dedicated`, que lo rechazaría por no estar en su mapeo. El test pasaría o
    fallaría por el motivo equivocado.

    `label` sigue expresándose en el vocabulario del CONTRATO (`clickbait` /
    `factual news`) porque es como lo escriben los tests; se traduce aquí al del
    modelo, que es lo que `dedicated` espera recibir y normalizar.
    """

    _AL_MODELO: ClassVar[dict[str, str]] = {
        "clickbait": "Clickbait",
        "factual news": "Not Clickbait",
    }

    def __init__(self, label="clickbait", sentiment="neutral", delay=0.0):
        self.label, self.sentiment, self.delay = label, sentiment, delay

    async def zero_shot(self, text, model, labels):
        await asyncio.sleep(self.delay)
        return ToolResult.ok({"label": self.label, "score": 0.91})

    async def classify(self, text, model):
        await asyncio.sleep(self.delay)
        if model == dedicated.MODEL:
            return ToolResult.ok({"label": self._AL_MODELO[self.label], "score": 0.91})
        return ToolResult.ok({"label": self.sentiment, "score": 0.84})


async def _falla(*args, **kwargs):
    return ToolResult.fail("el proveedor no respondió")


class _FakeDetector:
    def __init__(self, similarity=0.61, delay=0.0):
        self.similarity, self.delay = similarity, delay

    async def detect(self, headline, content):
        await asyncio.sleep(self.delay)
        return ToolResult.ok(
            {
                "similarity": self.similarity,
                "incoherent": self.similarity < 0.3,
                "headline": headline,
                "content": content,
            }
        )


@pytest.fixture
def señales(monkeypatch):
    """Instala los dobles. Devuelve una función para configurarlos por test."""

    def instalar(
        *,
        label="clickbait",
        sentiment="neutral",
        similarity=0.61,
        lexico=True,
        lineal=True,
        delay=0.0,
    ):
        monkeypatch.setattr(orchestrator, "_api", _FakeAPI(label, sentiment, delay))
        monkeypatch.setattr(orchestrator, "_detector", _FakeDetector(similarity, delay))

        def fake_lexical(headline):
            time.sleep(delay)
            return ToolResult.ok(
                {
                    "score": 2 if lexico else 0,
                    "is_clickbait": lexico,
                    "matches": [],
                    "headline": headline,
                }
            )

        def fake_linear(headline):
            time.sleep(delay)
            return ToolResult.ok(
                {
                    "is_clickbait": lineal,
                    "probability": 0.88 if lineal else 0.12,
                    "top_cues": [],
                    "headline": headline,
                }
            )

        monkeypatch.setattr(lexical, "detect", fake_lexical)
        monkeypatch.setattr(linear, "predict", fake_linear)

    return instalar


def _signal(name, is_clickbait, status=SignalStatus.OK):
    return _build(_SPECS[name], status, is_clickbait=is_clickbait)


def _por_dimension(verdicts):
    return {v.dimension: v for v in verdicts}


# ----- Validación de entrada -----


@pytest.mark.parametrize("blanco", [" ", "", "\t\n", "   "])
def test_headline_en_blanco_se_rechaza(blanco):
    # Un titular de solo espacios medía 1 carácter y pasaba `min_length=1`,
    # produciendo un 200 con `no_data` en lugar de un 422.
    with pytest.raises(ValidationError):
        AnalyzeRequest(headline=blanco)


def test_headline_se_normaliza():
    assert AnalyzeRequest(headline="  Breaking News  ").headline == "Breaking News"


# ----- _aggregate: invariantes 1 y 2 -----


def test_señales_de_acuerdo_dan_veredicto_de_dimension(señales):
    verdicts = _por_dimension(
        _aggregate(
            [
                _signal("detect_clickbait", True),
                _signal("detect_clickbait_lexical", True),
                _signal("detect_clickbait_linear", True),
            ]
        )
    )
    assert verdicts[Dimension.FORM].is_clickbait is True
    assert len(verdicts[Dimension.FORM].contributing) == 3


def test_señales_en_discrepancia_no_se_resuelven_por_mayoria():
    # Dos a uno NO gana: la discrepancia se declara, no se promedia.
    # La terna vuelve a darse en producción desde #115, que devolvió el voto a
    # la señal dedicada. Entre #109 y #115 no se daba, y el test siguió siendo
    # correcto igualmente: la invariante es de `_aggregate`, que debe aguantar
    # los votantes que le lleguen, no de quién vote esta semana.
    verdicts = _por_dimension(
        _aggregate(
            [
                _signal("detect_clickbait", False),
                _signal("detect_clickbait_lexical", True),
                _signal("detect_clickbait_linear", True),
            ]
        )
    )
    assert verdicts[Dimension.FORM].is_clickbait is None
    assert len(verdicts[Dimension.FORM].contributing) == 3


def test_veredicto_negativo_cuenta_como_voto():
    # Regresión: con `if not signal.is_clickbait` en vez de `is None`, los votos
    # False se descartarían y un titular factual saldría no_data.
    verdicts = _por_dimension(_aggregate([_signal("detect_clickbait_lexical", False)]))
    assert verdicts[Dimension.FORM].is_clickbait is False


def test_el_tono_no_vota_y_no_genera_dimension():
    verdicts = _aggregate(
        [
            _signal("analyze_sentiment", None),
            _signal("detect_clickbait_lexical", True),
        ]
    )
    assert Dimension.TONE not in _por_dimension(verdicts)


@pytest.mark.asyncio
async def test_la_señal_dedicada_vota_y_su_etiqueta_va_normalizada(señales):
    """#115 devuelve el voto que #109 había quitado, y fija la normalización.

    Las dos cosas van juntas a propósito. El voto depende de que el veredicto se
    extraiga con ``d["label"] == "clickbait"``, y el modelo de debajo dice
    ``Clickbait``: si la traducción de ``dedicated`` se cayera, la comparación
    no casaría, TODOS los titulares saldrían factuales y ningún test de voto lo
    notaría — porque seguiría habiendo voto, sólo que siempre el mismo.
    """
    señales(label="clickbait")
    signals = {s.name: s for s in await _run_signals("Un titular", None)}

    dedicada = signals["detect_clickbait"]
    assert dedicada.status == SignalStatus.OK
    assert dedicada.is_clickbait is True
    assert dedicada.data["label"] == "clickbait"  # no «Clickbait»

    forma = _por_dimension(_aggregate(list(signals.values())))[Dimension.FORM]
    assert forma.contributing == [
        "detect_clickbait",
        "detect_clickbait_lexical",
        "detect_clickbait_linear",
    ]


@pytest.mark.asyncio
async def test_una_etiqueta_desconocida_del_modelo_no_pasa_por_factual(
    señales, monkeypatch
):
    """El fallo silencioso que más caro sale: el modelo cambia de convención.

    Si `dedicated` dejara pasar la etiqueta cruda, el extractor la compararía
    con «clickbait», no coincidiría, y la señal declararía factual TODO sin que
    nada fallara. Tiene que degradarse a error, que sí se ve.
    """
    señales()

    async def responde_raro(text, model):
        return ToolResult.ok({"label": "LABEL_0", "score": 0.9})

    monkeypatch.setattr(orchestrator._api, "classify", responde_raro)
    signals = {s.name: s for s in await _run_signals("Un titular", None)}

    dedicada = signals["detect_clickbait"]
    assert dedicada.status == SignalStatus.ERROR
    assert dedicada.is_clickbait is None
    assert "LABEL_0" in dedicada.detail  # dice QUÉ llegó, para poder arreglarlo


def test_señal_fallida_no_genera_dimension():
    verdicts = _aggregate(
        [_signal("detect_clickbait_incoherence", None, SignalStatus.ERROR)]
    )
    assert verdicts == []


# ----- _overall: invariante 3 -----


def _dim(dimension, is_clickbait):
    return DimensionVerdict(dimension=dimension, is_clickbait=is_clickbait)


def test_sin_dimensiones_es_sin_datos():
    # Debe comprobarse ANTES que la ambigüedad: con la lista vacía el any() da
    # False y caería en FACTUAL, declarando factual lo que nadie pudo analizar.
    assert _overall([]) == OverallVerdict.NO_DATA


def test_el_engaño_pesa_mas_que_la_forma():
    # Tres señales de forma dicen "no" y una de engaño dice "sí": gana la de
    # engaño. Por mayoría saldría "factual", que es justo el error a evitar.
    verdict = _overall([_dim(Dimension.FORM, False), _dim(Dimension.DECEPTION, True)])
    assert verdict == OverallVerdict.DECEPTIVE


def test_forma_sin_engaño_es_clickbait_de_forma():
    verdict = _overall([_dim(Dimension.FORM, True), _dim(Dimension.DECEPTION, False)])
    assert verdict == OverallVerdict.STYLISTIC_CLICKBAIT


def test_todo_negativo_es_factual():
    verdict = _overall([_dim(Dimension.FORM, False), _dim(Dimension.DECEPTION, False)])
    assert verdict == OverallVerdict.FACTUAL


def test_dimension_sin_resolver_es_ambiguo():
    verdict = _overall([_dim(Dimension.FORM, None), _dim(Dimension.DECEPTION, False)])
    assert verdict == OverallVerdict.AMBIGUOUS


def test_una_deteccion_positiva_pesa_mas_que_una_discrepancia():
    # Decisión consciente: la ambigüedad de forma no oculta el engaño detectado.
    # Sigue visible en dimensions[], solo no manda en la etiqueta única.
    verdict = _overall([_dim(Dimension.FORM, None), _dim(Dimension.DECEPTION, True)])
    assert verdict == OverallVerdict.DECEPTIVE


# ----- _run_signals: aplicabilidad, aislamiento, orden -----


@pytest.mark.asyncio
async def test_sin_cuerpo_la_incoherencia_queda_no_aplicable(señales):
    señales()
    signals = {s.name: s for s in await _run_signals("Un titular", None)}

    incoherencia = signals["detect_clickbait_incoherence"]
    assert incoherencia.status == SignalStatus.NOT_APPLICABLE
    assert incoherencia.is_clickbait is None
    assert incoherencia.detail  # explica por qué, para pintarla en gris
    # Las demás sí corren.
    assert signals["detect_clickbait_lexical"].status == SignalStatus.OK


@pytest.mark.asyncio
@pytest.mark.parametrize("cuerpo", [None, "", "   "])
async def test_cuerpo_en_blanco_equivale_a_no_tenerlo(señales, cuerpo):
    señales()
    signals = {s.name: s for s in await _run_signals("Un titular", cuerpo)}
    assert signals["detect_clickbait_incoherence"].status == SignalStatus.NOT_APPLICABLE


@pytest.mark.asyncio
async def test_una_señal_que_revienta_no_tumba_a_las_demas(señales, monkeypatch):
    señales()

    # Se rompe SÓLO el modelo dedicado, no el método. Desde #115 el tono comparte
    # `classify` con él, así que parchear el método entero tumbaría dos señales y
    # el test dejaría de probar lo que dice: que las demás sobreviven.
    original = orchestrator._api.classify

    async def revienta_solo_el_dedicado(text, model):
        if model == dedicated.MODEL:
            raise TimeoutError("el proveedor no respondió")
        return await original(text, model)

    monkeypatch.setattr(orchestrator._api, "classify", revienta_solo_el_dedicado)

    signals = {s.name: s for s in await _run_signals("Un titular", "Un cuerpo")}

    caida = signals["detect_clickbait"]
    assert caida.status == SignalStatus.ERROR
    assert caida.is_clickbait is None
    assert "TimeoutError" in caida.detail  # tipo + mensaje, para depurar
    # Las otras cuatro sobreviven: ese es el punto de return_exceptions=True.
    otras = [s for n, s in signals.items() if n != "detect_clickbait"]
    assert all(s.status == SignalStatus.OK for s in otras)


@pytest.mark.asyncio
async def test_tool_result_fail_se_traduce_a_error_con_su_mensaje(señales, monkeypatch):
    señales()
    monkeypatch.setattr(
        lexical, "detect", lambda h: ToolResult.fail("El titular está vacío")
    )

    signals = {s.name: s for s in await _run_signals("Un titular", "Un cuerpo")}
    assert signals["detect_clickbait_lexical"].status == SignalStatus.ERROR
    assert signals["detect_clickbait_lexical"].detail == "El titular está vacío"


@pytest.mark.asyncio
async def test_un_formato_inesperado_se_aisla_como_error(señales, monkeypatch):
    # Si una tool cambia de formato, el KeyError del extractor sube al gather y
    # degrada esa señal sola, en vez de devolver un 500.
    señales()
    monkeypatch.setattr(lexical, "detect", lambda h: ToolResult.ok({"otra_clave": 1}))

    signals = {s.name: s for s in await _run_signals("Un titular", "Un cuerpo")}
    assert signals["detect_clickbait_lexical"].status == SignalStatus.ERROR
    assert "KeyError" in signals["detect_clickbait_lexical"].detail


@pytest.mark.asyncio
async def test_el_orden_de_las_señales_es_estable(señales):
    señales()
    con_cuerpo = [s.name for s in await _run_signals("Un titular", "Un cuerpo")]
    sin_cuerpo = [s.name for s in await _run_signals("Un titular", None)]

    # Aunque una se salte, la interfaz recibe siempre las tarjetas en el mismo
    # orden: el de _SIGNALS, no el de finalización.
    assert con_cuerpo == sin_cuerpo == [spec.name for spec in _SIGNALS]


@pytest.mark.asyncio
async def test_las_señales_corren_en_paralelo(señales):
    # La razón de ser del gather: el coste es el de la más lenta, no la suma.
    señales(delay=0.1)

    inicio = time.perf_counter()
    await _run_signals("Un titular", "Un cuerpo")
    transcurrido = time.perf_counter() - inicio

    assert transcurrido < 0.3  # secuencial serían ~0.5 s


@pytest.mark.asyncio
async def test_la_dimension_y_el_tipo_salen_de_la_ficha(señales):
    señales()
    signals = {s.name: s for s in await _run_signals("Un titular", "Un cuerpo")}

    assert signals["detect_clickbait_incoherence"].dimension == Dimension.DECEPTION
    assert signals["analyze_sentiment"].dimension == Dimension.TONE
    assert signals["detect_clickbait_lexical"].dimension == Dimension.FORM


@pytest.mark.asyncio
async def test_la_etiqueta_legible_sale_de_la_ficha(señales):
    """El `label` viaja desde la ficha, y esto es lo que impide que se copie.

    Antes de #133 la interfaz mantenía su propio diccionario de nombres en
    `vocabulario.ts`. Renombrar una señal aquí no rompía nada: sólo hacía que la
    pantalla pintara el id crudo, en silencio. Es la forma exacta de #116, y este
    test es lo que la cierra — se compara contra la ficha, no contra una cadena
    escrita a mano, así que cambiar el nombre en un sitio no puede desalinearlos.
    """
    señales()
    fichas = cards_by_signal()
    signals = await _run_signals("Un titular", "Un cuerpo")

    assert signals, "sin señales no se está comprobando nada"
    for signal in signals:
        assert signal.label == fichas[signal.name]["name"]


# ----- analyze: extremo a extremo (con dobles) -----


@pytest.mark.asyncio
async def test_clickbait_de_forma_con_cuerpo_coherente(señales):
    señales(label="clickbait", lexico=True, lineal=True, similarity=0.61)

    response = await orchestrator.analyze(
        AnalyzeRequest(headline="You Won't Believe What Happened Next", content="...")
    )

    assert response.verdict == OverallVerdict.STYLISTIC_CLICKBAIT
    assert response.has_any_result
    assert len(response.signals) == len(_SIGNALS)
    # El tono aparece como tarjeta pero no como dimensión.
    assert "analyze_sentiment" in {s.name for s in response.signals}
    assert Dimension.TONE not in {d.dimension for d in response.dimensions}


@pytest.mark.asyncio
async def test_forma_sobria_pero_engañosa(señales):
    # Las dos señales de forma que votan dicen "no es clickbait" y solo la
    # incoherencia dice que sí. (El zero-shot corre pero no vota desde #109.)
    señales(label="factual news", lexico=False, lineal=False, similarity=0.22)

    response = await orchestrator.analyze(
        AnalyzeRequest(headline="Report Details Q3 Financial Results", content="...")
    )

    assert response.verdict == OverallVerdict.DECEPTIVE
    dimensiones = _por_dimension(response.dimensions)
    assert dimensiones[Dimension.FORM].is_clickbait is False
    assert dimensiones[Dimension.DECEPTION].is_clickbait is True


@pytest.mark.asyncio
async def test_si_todas_las_señales_fallan_no_hay_veredicto(señales, monkeypatch):
    señales()
    for modulo, atributo in ((lexical, "detect"), (linear, "predict")):
        monkeypatch.setattr(modulo, atributo, lambda h: ToolResult.fail("caído"))
    for metodo in ("zero_shot", "classify"):
        monkeypatch.setattr(orchestrator._api, metodo, _falla)

    response = await orchestrator.analyze(AnalyzeRequest(headline="Un titular"))

    assert response.verdict == OverallVerdict.NO_DATA
    assert not response.has_any_result
    assert response.dimensions == []
    # Aun así la respuesta es informativa: cada tarjeta dice qué le pasó.
    assert all(s.detail for s in response.signals)
