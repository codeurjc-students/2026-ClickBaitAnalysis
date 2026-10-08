"""Tests de la orquestación de /analyze.

Ninguno toca la red ni carga modelos: se sustituyen las cuatro fuentes reales
(el backend NLP, el detector de incoherencia, `lexical.detect` y
`linear.predict`) por dobles controlables.

**Se parchean las funciones de la FACTORÍA**, no unas globales del orquestador.
Hasta #119 el backend vivía en `orchestrator._api`, y parchear ese atributo
funcionaba pero probaba una forma que ya no existe: ahora las lambdas de
`_SIGNALS` piden el cliente a `get_nlp_backend()` en cada llamada. Sustituir la
función es lo que sigue el camino real, y de paso deja de depender de que el
orquestador guarde el cliente en algún sitio.
"""

import asyncio
import time
from types import SimpleNamespace
from typing import ClassVar

import pytest
from pydantic import ValidationError
from structlog.testing import capture_logs

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
from backend.config.settings import ModeloConInvocacion, settings
from backend.core.idioma import ESPANOL, INDETERMINADO, INGLES
from backend.core.models import ToolResult
from backend.integrations.nlp import dedicated, lexical, linear
from backend.integrations.nlp.factory import (
    motivo_si_el_cuerpo_no_se_compara,
    motivo_si_no_se_analiza,
)
from backend.integrations.nlp.model_cards import fichas_en

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
        api = _FakeAPI(label, sentiment, delay)
        detector = _FakeDetector(similarity, delay)
        monkeypatch.setattr(orchestrator, "get_nlp_backend", lambda: api)
        monkeypatch.setattr(
            orchestrator, "get_incoherence_detector", lambda idioma: detector
        )

        # Con la firma de los de verdad: desde #93 reciben el umbral y el tope
        # de pistas de la factoría.
        def fake_lexical(headline, threshold):
            time.sleep(delay)
            return ToolResult.ok(
                {
                    "score": 2 if lexico else 0,
                    "is_clickbait": lexico,
                    "threshold": threshold,
                    "matches": [],
                    "headline": headline,
                }
            )

        def fake_linear(headline, top_cues):
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

        # Se devuelven para los tests que necesitan romper UN método concreto
        # del doble. Antes se alcanzaban por `orchestrator._api`; ahora el
        # orquestador no los guarda, así que los reparte quien los crea.
        return SimpleNamespace(api=api, detector=detector)

    return instalar


def _signal(name, is_clickbait, status=SignalStatus.OK):
    return _build(_SPECS[name], status, idioma=INGLES, is_clickbait=is_clickbait)


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
    signals = {s.name: s for s in await _run_signals("Un titular", None, INGLES, None)}

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
    dobles = señales()

    async def responde_raro(text, model):
        return ToolResult.ok({"label": "LABEL_0", "score": 0.9})

    monkeypatch.setattr(dobles.api, "classify", responde_raro)
    signals = {s.name: s for s in await _run_signals("Un titular", None, INGLES, None)}

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


def test_contra_una_forma_unanime_el_engano_no_manda():
    # Las tres señales de forma dicen "no" y la de engaño dice "sí". Hasta
    # #124 ganaba el engaño, pero ahí acertaba el 13 % (165 pares de Webis-17):
    # la discrepancia es entre dimensiones, y se declara en vez de resolverse.
    # Por mayoría saldría "factual", que tampoco: se declara.
    verdict = _overall([_dim(Dimension.FORM, False), _dim(Dimension.DECEPTION, True)])
    assert verdict == OverallVerdict.AMBIGUOUS


def test_engano_y_forma_de_acuerdo_es_enganoso():
    verdict = _overall([_dim(Dimension.FORM, True), _dim(Dimension.DECEPTION, True)])
    assert verdict == OverallVerdict.DECEPTIVE


def test_sin_forma_el_engano_manda():
    # Si no votó ninguna señal de forma, no hay con qué discrepar (#124).
    assert _overall([_dim(Dimension.DECEPTION, True)]) == OverallVerdict.DECEPTIVE


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
    # Con la forma dividida, el engaño desempata: ahí acertaba el 68 % (862
    # pares de Webis-17, #124). La discrepancia de forma sigue visible en
    # dimensions[]; sólo no manda en la etiqueta única.
    verdict = _overall([_dim(Dimension.FORM, None), _dim(Dimension.DECEPTION, True)])
    assert verdict == OverallVerdict.DECEPTIVE


# ----- _run_signals: aplicabilidad, aislamiento, orden -----


@pytest.mark.asyncio
async def test_sin_cuerpo_la_incoherencia_queda_no_aplicable(señales):
    señales()
    signals = {s.name: s for s in await _run_signals("Un titular", None, INGLES, None)}

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
    signals = {
        s.name: s for s in await _run_signals("Un titular", cuerpo, INGLES, INGLES)
    }
    assert signals["detect_clickbait_incoherence"].status == SignalStatus.NOT_APPLICABLE


@pytest.mark.asyncio
@pytest.mark.parametrize("ausente", ["None", "none", " None ", "null"])
async def test_un_cuerpo_que_solo_dice_none_no_es_un_cuerpo(señales, ausente):
    """#197: el modelo del agente mandó `content="None"`, la incoherencia comparó
    el titular con esa palabra y el veredicto salió `deceptive`. La similitud
    baja del doble es la que habría salido: si la señal llegara a medirse, lo
    marcaría como engaño."""
    señales(similarity=0.12)

    resultado = await orchestrator.analyze(
        AnalyzeRequest(
            headline="You Won't Believe What This Dog Did Next", content=ausente
        )
    )

    signals = {s.name: s for s in resultado.signals}
    assert signals["detect_clickbait_incoherence"].status == SignalStatus.NOT_APPLICABLE
    assert resultado.verdict != OverallVerdict.DECEPTIVE
    assert resultado.content is None


@pytest.mark.asyncio
async def test_una_señal_que_revienta_no_tumba_a_las_demas(señales, monkeypatch):
    dobles = señales()

    # Se rompe SÓLO el modelo dedicado, no el método. Desde #115 el tono comparte
    # `classify` con él, así que parchear el método entero tumbaría dos señales y
    # el test dejaría de probar lo que dice: que las demás sobreviven.
    original = dobles.api.classify

    async def revienta_solo_el_dedicado(text, model):
        if model == dedicated.MODEL:
            raise TimeoutError("el proveedor no respondió")
        return await original(text, model)

    monkeypatch.setattr(dobles.api, "classify", revienta_solo_el_dedicado)

    signals = {
        s.name: s for s in await _run_signals("Un titular", "Un cuerpo", INGLES, INGLES)
    }

    caida = signals["detect_clickbait"]
    assert caida.status == SignalStatus.ERROR
    assert caida.is_clickbait is None
    # Desde #89 el detalle dice QUÉ pasó, no CÓMO está hecho esto: el tipo de la
    # excepción y su mensaje van al log, que es donde se depura.
    assert caida.detail == "La señal tardó demasiado en responder."
    assert "TimeoutError" not in caida.detail
    # Las otras cuatro sobreviven: ese es el punto de return_exceptions=True.
    otras = [s for n, s in signals.items() if n != "detect_clickbait"]
    assert all(s.status == SignalStatus.OK for s in otras)


@pytest.mark.asyncio
async def test_tool_result_fail_se_traduce_a_error_con_su_mensaje(señales, monkeypatch):
    señales()
    monkeypatch.setattr(
        lexical,
        "detect",
        lambda titular, umbral: ToolResult.fail("El titular está vacío"),
    )

    signals = {
        s.name: s for s in await _run_signals("Un titular", "Un cuerpo", INGLES, INGLES)
    }
    assert signals["detect_clickbait_lexical"].status == SignalStatus.ERROR
    assert signals["detect_clickbait_lexical"].detail == "El titular está vacío"


@pytest.mark.asyncio
async def test_un_formato_inesperado_se_aisla_como_error(señales, monkeypatch):
    # Si una tool cambia de formato, el KeyError del extractor sube al gather y
    # degrada esa señal sola, en vez de devolver un 500.
    señales()
    monkeypatch.setattr(
        lexical, "detect", lambda titular, umbral: ToolResult.ok({"otra_clave": 1})
    )

    signals = {
        s.name: s for s in await _run_signals("Un titular", "Un cuerpo", INGLES, INGLES)
    }
    caida = signals["detect_clickbait_lexical"]
    assert caida.status == SignalStatus.ERROR
    # `KeyError: 'is_clickbait'` le contaba a cualquiera cómo está estructurado
    # el código por dentro (#89). Ahora eso vive en el log.
    assert "KeyError" not in caida.detail
    assert "no previsto" in caida.detail


@pytest.mark.asyncio
async def test_el_fallo_entero_se_registra_aunque_no_se_publique(señales, monkeypatch):
    """Lo que sale de la respuesta tiene que aparecer en el log (#89).

    Sanear sin registrar no arregla, destruye: hasta esta issue el `detail` era
    el ÚNICO sitio donde existía el motivo de un fallo imprevisto, porque el
    orquestador no registraba nada.
    """
    señales()
    monkeypatch.setattr(
        lexical, "detect", lambda titular, umbral: ToolResult.ok({"otra_clave": 1})
    )

    with capture_logs() as registrado:
        signals = {
            s.name: s
            for s in await _run_signals("Un titular", "Un cuerpo", INGLES, INGLES)
        }

    caida = signals["detect_clickbait_lexical"]
    fallo = next(linea for linea in registrado if linea["event"] == "senal.fallo")

    assert fallo["signal"] == "detect_clickbait_lexical"
    assert fallo["tipo"] == "KeyError"
    assert "is_clickbait" in fallo["detalle"]
    assert "Traceback" in fallo["traza"]
    # Y nada de eso está en lo que se publica.
    assert "KeyError" not in caida.detail
    assert "is_clickbait" not in caida.detail


@pytest.mark.asyncio
async def test_la_respuesta_no_publica_interioridad(señales, monkeypatch):
    """Sobre la respuesta ENTERA, no sobre un campo: un sitio nuevo que vuelque
    el texto de una excepción queda cubierto sin acordarse de él."""
    dobles = señales()

    async def revienta(text, model):
        raise RuntimeError("/app/backend/integrations/nlp/local.py falló")

    monkeypatch.setattr(dobles.api, "classify", revienta)
    monkeypatch.setattr(
        lexical, "detect", lambda titular, umbral: ToolResult.ok({"otra_clave": 1})
    )

    respuesta = await orchestrator.analyze(
        AnalyzeRequest(headline="Un titular", content="Un cuerpo")
    )
    entera = respuesta.model_dump_json()

    for rastro in ("RuntimeError", "KeyError", "Traceback", "/app/backend", ".py"):
        assert rastro not in entera, rastro


@pytest.mark.asyncio
async def test_el_orden_de_las_señales_es_estable(señales):
    señales()
    con_cuerpo = [
        s.name for s in await _run_signals("Un titular", "Un cuerpo", INGLES, INGLES)
    ]
    sin_cuerpo = [s.name for s in await _run_signals("Un titular", None, INGLES, None)]

    # Aunque una se salte, la interfaz recibe siempre las tarjetas en el mismo
    # orden: el de _SIGNALS, no el de finalización.
    assert con_cuerpo == sin_cuerpo == [spec.name for spec in _SIGNALS]


@pytest.mark.asyncio
async def test_las_señales_corren_en_paralelo(señales):
    # La razón de ser del gather: el coste es el de la más lenta, no la suma.
    señales(delay=0.1)

    inicio = time.perf_counter()
    await _run_signals("Un titular", "Un cuerpo", INGLES, INGLES)
    transcurrido = time.perf_counter() - inicio

    assert transcurrido < 0.3  # secuencial serían ~0.5 s


@pytest.mark.asyncio
async def test_la_dimension_y_el_tipo_salen_de_la_ficha(señales):
    señales()
    signals = {
        s.name: s for s in await _run_signals("Un titular", "Un cuerpo", INGLES, INGLES)
    }

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
    fichas = fichas_en(INGLES)
    signals = await _run_signals("Un titular", "Un cuerpo", INGLES, INGLES)

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
async def test_forma_sobria_y_cuerpo_incoherente_es_ambiguo(señales):
    # Las tres señales de forma dicen "no es clickbait" y sólo la incoherencia
    # dice que sí: desde #124 no la pisa, y se declara la discrepancia.
    señales(label="factual news", lexico=False, lineal=False, similarity=0.22)

    response = await orchestrator.analyze(
        AnalyzeRequest(headline="Report Details Q3 Financial Results", content="...")
    )

    assert response.verdict == OverallVerdict.AMBIGUOUS
    dimensiones = _por_dimension(response.dimensions)
    assert dimensiones[Dimension.FORM].is_clickbait is False
    assert dimensiones[Dimension.DECEPTION].is_clickbait is True


@pytest.mark.asyncio
async def test_forma_dividida_y_cuerpo_incoherente_es_enganoso(señales):
    # La dedicada dice que sí y el léxico y el lineal que no: la forma queda
    # dividida, y la incoherencia desempata (#124).
    señales(label="clickbait", lexico=False, lineal=False, similarity=0.22)

    response = await orchestrator.analyze(
        AnalyzeRequest(headline="Report Details Q3 Financial Results", content="...")
    )

    assert response.verdict == OverallVerdict.DECEPTIVE
    dimensiones = _por_dimension(response.dimensions)
    assert dimensiones[Dimension.FORM].is_clickbait is None
    assert dimensiones[Dimension.DECEPTION].is_clickbait is True


@pytest.mark.asyncio
async def test_si_todas_las_señales_fallan_no_hay_veredicto(señales, monkeypatch):
    dobles = señales()
    for modulo, atributo in ((lexical, "detect"), (linear, "predict")):
        monkeypatch.setattr(
            modulo, atributo, lambda titular, ajuste: ToolResult.fail("caído")
        )
    for metodo in ("zero_shot", "classify"):
        monkeypatch.setattr(dobles.api, metodo, _falla)

    response = await orchestrator.analyze(AnalyzeRequest(headline="Un titular"))

    assert response.verdict == OverallVerdict.NO_DATA
    assert not response.has_any_result
    assert response.dimensions == []
    # Aun así la respuesta es informativa: cada tarjeta dice qué le pasó.
    assert all(s.detail for s in response.signals)


# ----- La puerta del idioma (#229) -----
#
# Un titular que no está en inglés no se analiza: hasta #229 recibía un
# veredicto sin aviso (en TA1C, «factual» en el 79,7 % de los teasers).

TITULAR_EN_ESPANOL = (
    "No vas a creer lo que hizo este perro cuando su dueño volvió a casa"
)


def _espiar(monkeypatch, dobles):
    """Apunta cada llamada a un detector —el backend NLP, el de incoherencia, el
    léxico y el lineal— sin cambiar lo que devuelven. Devuelve esa lista."""
    llamadas = []

    def apuntar(nombre, funcion):
        def envuelta(*args, **kwargs):
            llamadas.append(nombre)
            return funcion(*args, **kwargs)

        return envuelta

    for metodo in ("classify", "zero_shot"):
        monkeypatch.setattr(
            dobles.api, metodo, apuntar(metodo, getattr(dobles.api, metodo))
        )
    monkeypatch.setattr(
        dobles.detector, "detect", apuntar("incoherencia", dobles.detector.detect)
    )
    monkeypatch.setattr(lexical, "detect", apuntar("lexico", lexical.detect))
    monkeypatch.setattr(linear, "predict", apuntar("lineal", linear.predict))
    return llamadas


@pytest.mark.asyncio
async def test_un_titular_en_espanol_no_se_analiza(señales, monkeypatch):
    """Mientras ninguna señal tenga modelo en español (llegan con C–E de
    `v0.8`), ninguna lo analiza. Desde #230 cada una lo dice con su motivo, y el
    léxico con el suyo: no es que le falte un modelo, es que no lo tiene."""
    llamadas = _espiar(monkeypatch, señales())

    response = await orchestrator.analyze(AnalyzeRequest(headline=TITULAR_EN_ESPANOL))

    assert response.language == ESPANOL
    assert response.verdict == OverallVerdict.NO_DATA
    assert response.dimensions == []
    # Todas las tarjetas, en su orden de siempre, y cada una dice por qué.
    assert [senal.name for senal in response.signals] == [
        spec.name for spec in _SIGNALS
    ]
    for senal in response.signals:
        assert senal.status == SignalStatus.NOT_APPLICABLE
        assert senal.detail == motivo_si_no_se_analiza(senal.name, ESPANOL)
    lexico = next(
        senal for senal in response.signals if senal.name == "detect_clickbait_lexical"
    )
    assert "léxico" in (lexico.detail or "")
    assert llamadas == []


@pytest.mark.asyncio
async def test_en_espanol_se_ejecuta_solo_la_senal_con_modelo(señales, monkeypatch):
    """#230: el español se activa señal a señal. Con un modelo en español puesto
    por configuración —el experimento con el que D (#232) medirá un zero-shot
    multilingüe—, la dedicada se ejecuta con ESE modelo y se rotula con él, y
    las demás siguen sin analizar el titular."""
    dobles = señales()
    llamadas = _espiar(monkeypatch, dobles)
    modelos = []
    zero_shot = dobles.api.zero_shot

    async def apuntar_modelo(text, model, labels):
        modelos.append(model)
        return await zero_shot(text, model, labels)

    monkeypatch.setattr(dobles.api, "zero_shot", apuntar_modelo)
    monkeypatch.setattr(
        settings,
        "nlp_models_es",
        {
            "detect_clickbait": ModeloConInvocacion(
                id="prueba/multilingue", task="zero-shot-classification"
            )
        },
    )

    response = await orchestrator.analyze(AnalyzeRequest(headline=TITULAR_EN_ESPANOL))

    por_nombre = {senal.name: senal for senal in response.signals}
    dedicada = por_nombre.pop("detect_clickbait")
    assert dedicada.status == SignalStatus.OK
    assert modelos == ["prueba/multilingue"]
    assert "prueba/multilingue" in dedicada.label
    assert all(
        senal.status == SignalStatus.NOT_APPLICABLE for senal in por_nombre.values()
    )
    assert llamadas == ["zero_shot"]
    # Una sola señal de forma votó, y en «sí»: el veredicto sale de ella.
    assert response.verdict == OverallVerdict.STYLISTIC_CLICKBAIT


@pytest.mark.asyncio
async def test_otro_idioma_se_nombra_como_otro_idioma(señales, monkeypatch):
    llamadas = _espiar(monkeypatch, señales())

    response = await orchestrator.analyze(
        AnalyzeRequest(
            headline="Le gouvernement annonce une nouvelle réforme des retraites"
        )
    )

    assert response.language == INDETERMINADO
    assert response.verdict == OverallVerdict.NO_DATA
    assert all("otro idioma" in (senal.detail or "") for senal in response.signals)
    assert llamadas == []


@pytest.mark.asyncio
async def test_un_titular_en_ingles_se_analiza_y_lleva_su_idioma(señales, monkeypatch):
    """La otra mitad: sin ella, una puerta que lo cerrara todo pasaría las dos
    de arriba."""
    llamadas = _espiar(monkeypatch, señales())

    response = await orchestrator.analyze(
        AnalyzeRequest(headline="You Won't Believe What Happened Next", content="...")
    )

    assert response.language == INGLES
    assert response.verdict == OverallVerdict.STYLISTIC_CLICKBAIT
    assert all(senal.status == SignalStatus.OK for senal in response.signals)
    assert set(llamadas) == {"classify", "incoherencia", "lexico", "lineal"}


TITULAR_DE_LA_FED = "Federal Reserve Holds Interest Rates Steady"


def _incoherencia(response):
    return next(
        senal
        for senal in response.signals
        if senal.name == "detect_clickbait_incoherence"
    )


@pytest.mark.asyncio
async def test_un_cuerpo_en_espanol_no_se_compara_y_lo_demas_se_analiza(
    señales, monkeypatch
):
    """La incoherencia compara titular y cuerpo con un modelo inglés, y con el
    cuerpo en español la similitud se hunde aunque diga lo mismo. Las demás
    señales no leen el cuerpo: se analizan."""
    llamadas = _espiar(monkeypatch, señales())

    response = await orchestrator.analyze(
        AnalyzeRequest(
            headline=TITULAR_DE_LA_FED,
            content="La Reserva Federal mantuvo sin cambios su tipo de interés.",
        )
    )

    incoherencia = _incoherencia(response)
    assert response.language == INGLES
    assert incoherencia.status == SignalStatus.NOT_APPLICABLE
    assert incoherencia.detail == motivo_si_el_cuerpo_no_se_compara(ESPANOL)
    assert all(
        senal.status == SignalStatus.OK
        for senal in response.signals
        if senal is not incoherencia
    )
    assert "incoherencia" not in llamadas


@pytest.mark.asyncio
async def test_un_cuerpo_en_ingles_se_compara(señales, monkeypatch):
    llamadas = _espiar(monkeypatch, señales())

    response = await orchestrator.analyze(
        AnalyzeRequest(
            headline=TITULAR_DE_LA_FED,
            content="The Federal Reserve kept its benchmark interest rate unchanged.",
        )
    )

    assert _incoherencia(response).status == SignalStatus.OK
    assert "incoherencia" in llamadas


@pytest.mark.asyncio
async def test_con_ingles_run_signals_analiza_el_espanol_como_ingles(
    señales, monkeypatch
):
    """Desde #230 la puerta vive en `_run_signals`, y los idiomas los recibe:
    con `INGLES` en los dos, analiza un titular y un cuerpo en español como si
    fueran ingleses. Es lo que hace `eval_ta1c` para repetir el punto de partida
    de #229, el español tratado como inglés."""
    llamadas = _espiar(monkeypatch, señales())

    signals = await _run_signals(
        TITULAR_EN_ESPANOL, "El cuerpo de la noticia.", INGLES, INGLES
    )

    assert all(senal.status == SignalStatus.OK for senal in signals)
    assert set(llamadas) == {"classify", "incoherencia", "lexico", "lineal"}


# ----- precalentado (#125), medido de verdad (#138) -----
#
# Hasta #138 lo único probado era que el `lifespan` LLAMA a `precalentar`. Lo que
# hace por dentro —a qué señales toca, y qué pasa si una revienta— no lo
# recorría ningún test, y ahí vive la garantía de que un modelo que no carga no
# impide servir `/tools` ni `/history`.


@pytest.mark.asyncio
async def test_con_backend_local_se_calientan_las_tres(señales, monkeypatch):
    señales()
    monkeypatch.setattr(settings, "nlp_backend", "local")

    tiempos = await orchestrator.precalentar()

    assert set(tiempos) == {
        "detect_clickbait",
        "analyze_sentiment",
        "detect_clickbait_incoherence",
    }
    assert all(medida >= 0 for medida in tiempos.values())


@pytest.mark.asyncio
async def test_se_calienta_tambien_el_modelo_del_espanol(señales, monkeypatch):
    """#230: cada idioma que analiza cada señal, con la misma regla que la
    puerta. El inglés conserva sus etiquetas de siempre."""
    señales()
    monkeypatch.setattr(settings, "nlp_backend", "local")
    monkeypatch.setattr(
        settings, "nlp_models_es", {"analyze_sentiment": "prueba/tono-multilingue"}
    )

    tiempos = await orchestrator.precalentar()

    assert set(tiempos) == {
        "detect_clickbait",
        "analyze_sentiment",
        "analyze_sentiment (es)",
        "detect_clickbait_incoherence",
    }


@pytest.mark.asyncio
async def test_con_backend_remoto_solo_se_calienta_la_incoherencia(
    señales, monkeypatch
):
    """Con `remote`, las señales de titular van por HTTP a HuggingFace:
    calentar sus modelos en local sería cargar lo que no se va a usar. La
    incoherencia corre siempre aquí, así que sí se calienta."""
    señales()
    monkeypatch.setattr(settings, "nlp_backend", "remote")

    tiempos = await orchestrator.precalentar()

    assert set(tiempos) == {"detect_clickbait_incoherence"}


@pytest.mark.asyncio
async def test_una_señal_que_no_carga_no_impide_arrancar(señales, monkeypatch):
    """El fallo se registra con un tiempo NEGATIVO y no se propaga.

    Es lo que sostiene la decisión de #125 de precalentar bloqueando el
    arranque: si una excepción subiera, un modelo corrupto dejaría la API sin
    levantar entera, cuando `/tools` y `/history` no necesitan ningún modelo.
    """
    dobles = señales()
    monkeypatch.setattr(settings, "nlp_backend", "remote")

    async def revienta(headline, content):
        raise RuntimeError("el modelo no está")

    monkeypatch.setattr(dobles.detector, "detect", revienta)

    tiempos = await orchestrator.precalentar()

    assert tiempos["detect_clickbait_incoherence"] == -1.0


@pytest.mark.asyncio
async def test_el_data_de_cada_senal_dice_en_que_idioma_se_analizo(señales):
    """#230: el orquestador añade `language` a la salida de cada señal, como
    cada herramienta suelta. El contrato publica la misma forma para las dos."""
    señales()

    signals = await _run_signals("Un titular", "Un cuerpo", INGLES, INGLES)

    assert all(
        senal.data is not None and senal.data["language"] == INGLES for senal in signals
    )


def test_una_senal_suelta_se_rotula_con_la_ficha_de_su_idioma(monkeypatch):
    """La traza del agente sólo trae el `data`, y desde #230 el `data` dice su
    idioma: la tarjeta lleva la ficha de ese idioma, no la inglesa. Sin
    `language` —una salida de antes— se analizó en inglés."""
    monkeypatch.setattr(
        settings, "nlp_models_es", {"detect_clickbait": "prueba/multilingue"}
    )
    datos = {"label": "clickbait", "score": 0.9}

    en_espanol = orchestrator.senal_de("detect_clickbait", {**datos, "language": "es"})
    sin_idioma = orchestrator.senal_de("detect_clickbait", datos)

    assert en_espanol is not None and "prueba/multilingue" in en_espanol.label
    assert sin_idioma is not None and "prueba/multilingue" not in sin_idioma.label


@pytest.mark.asyncio
async def test_la_tarjeta_rotula_el_modelo_que_se_ejecuto(señales, monkeypatch):
    """La tercera puerta de la divergencia de #116, y la peor de las tres.

    Detectado ejecutando el sistema con otro modelo configurado: el catálogo y
    `describe_models` ya decían el efectivo, pero la tarjeta del análisis seguía
    rotulada «RoBERTa dedicado (entrenado en Webis-17)» — y ésa es justo la que
    mira quien lee el resultado.
    """
    señales()
    monkeypatch.setattr(settings, "nlp_models", {"detect_clickbait": "otra/cosa"})

    signals = {s.name: s for s in await _run_signals("Un titular", None, INGLES, None)}
    dedicada = signals["detect_clickbait"]

    assert "otra/cosa" in dedicada.label
    assert "Webis" not in dedicada.label
    # Lo que describe a la señal y no al modelo no cambia.
    assert dedicada.dimension == Dimension.FORM


# ----- Una señal suelta, fuera del análisis (#191) -----


@pytest.mark.parametrize(
    ("nombre", "datos", "voto"),
    [
        ("detect_clickbait", {"label": "clickbait", "score": 0.97}, True),
        (
            "detect_clickbait_lexical",
            {"score": 0, "is_clickbait": False, "matches": [], "headline": "x"},
            False,
        ),
        (
            "detect_clickbait_incoherence",
            {
                "similarity": 0.12,
                "incoherent": True,
                "threshold": 0.3,
                "headline": "x",
                "content": "y",
            },
            True,
        ),
        # El tono no vota, tampoco suelto.
        ("analyze_sentiment", {"label": "neutral", "score": 0.7}, None),
    ],
)
def test_una_senal_suelta_se_envuelve_con_la_regla_del_analisis(nombre, datos, voto):
    """El agente llama a veces a una señal sola, y su traza sólo trae el `data`.
    Para pintarla con la misma tarjeta que el análisis, el voto sale de la MISMA
    regla (`verdict`) y el rótulo, la dimensión y el tipo, de la misma ficha."""
    senal = orchestrator.senal_de(nombre, datos)

    assert senal is not None
    assert senal == _build(
        _SPECS[nombre], SignalStatus.OK, idioma=INGLES, is_clickbait=voto, data=datos
    )


@pytest.mark.parametrize(
    ("nombre", "datos"),
    [
        ("get_nyt_news", {"result": []}),  # no es una señal
        ("analyze_headline", {"headline": "x"}),  # es un análisis entero
        ("detect_clickbait_lexical", {"inesperado": True}),  # forma rota
        ("detect_clickbait", None),
    ],
    ids=["noticias", "analisis", "forma_rota", "sin_datos"],
)
def test_lo_que_no_es_una_senal_no_se_envuelve(nombre, datos):
    """`None` y no una tarjeta a medias: la interfaz lo pinta en crudo, que es
    degradar, no afirmar un voto que nadie ha calculado."""
    assert orchestrator.senal_de(nombre, datos) is None
