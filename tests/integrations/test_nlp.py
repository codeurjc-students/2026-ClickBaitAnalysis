import asyncio
import json

import pytest
import respx  # Usamos en vez de htttp, ya que no hacemos llamadas de verdad, mockeamos
from httpx import Response, TimeoutException
from mcp.server.fastmcp import FastMCP

from backend.config.settings import settings
from backend.integrations.nlp import lexical, linear, model_cards
from backend.integrations.nlp import tool as nlp_tool
from backend.integrations.nlp.client import HFClient
from backend.integrations.nlp.factory import get_nlp_backend
from backend.integrations.nlp.incoherence import IncoherenceDetector
from backend.integrations.nlp.local import LocalNLPClient

MODELS_URL = "https://router.huggingface.co/hf-inference/models/"


# -----HF CLIENT-----
# classify
@pytest.mark.asyncio
async def test_classify_returns_top_label():
    model = "distilbert/distilbert-base-uncased-finetuned-sst-2-english"
    payload = [
        [
            {"label": "POSITIVE", "score": 0.99},
            {"label": "NEGATIVE", "score": 0.01},
        ]
    ]  # respuesta doble-anidada [[{label, score}]]
    with respx.mock:
        respx.post(f"{MODELS_URL}{model}").mock(
            return_value=Response(200, json=payload)
        )
        result = await HFClient().classify("great movie", model)

    assert result.success
    assert result.data == {"label": "POSITIVE", "score": 0.99}


@pytest.mark.asyncio
async def test_classify_unexpected_shape_returns_fail():
    model = "some/model"
    with respx.mock:
        respx.post(f"{MODELS_URL}{model}").mock(
            return_value=Response(200, json={"unexpected": "shape"})
        )
        result = await HFClient().classify("text", model)

    assert not result.success
    assert result.error


@pytest.mark.asyncio
async def test_classify_http_error_propagates():
    model = "some/model"
    with respx.mock:
        route = respx.post(f"{MODELS_URL}{model}").mock(
            return_value=Response(
                500, text="Internal Server Error"
            )  # 500 para no propagar
        )
        result = await HFClient().classify("text", model)

    assert not result.success
    assert "500" in result.error
    assert route.call_count == 1  # Solo se llama una vez (usar count en reintentos)


# zero_shot


@pytest.mark.asyncio
async def test_zero_shot_returns_top_label():
    model = "facebook/bart-large-mnli"
    payload = [
        {"label": "clickbait", "score": 0.79},
        {"label": "factual news", "score": 0.21},
    ]
    with respx.mock:
        respx.post(f"{MODELS_URL}{model}").mock(
            return_value=Response(200, json=payload)
        )
        result = await HFClient().zero_shot(
            "headline", model, ["clickbait", "factual news"]
        )

    assert result.success
    assert result.data == {"label": "clickbait", "score": 0.79}


@pytest.mark.asyncio
async def test_zero_shot_sends_candidate_labels():
    model = "facebook/bart-large-mnli"
    labels = ["clickbait", "factual news"]
    with respx.mock:
        route = respx.post(f"{MODELS_URL}{model}").mock(
            return_value=Response(200, json=[{"label": "clickbait", "score": 0.9}])
        )
        await HFClient().zero_shot("headline", model, labels)

    # El cuerpo de la petición debe incluir inputs + candidate_labels.
    sent = json.loads(route.calls.last.request.content)
    assert sent["inputs"] == "headline"
    assert sent["parameters"]["candidate_labels"] == labels


# auth


@pytest.mark.asyncio
async def test_request_sends_bearer_header():
    model = "some/model"
    with respx.mock:
        route = respx.post(f"{MODELS_URL}{model}").mock(
            return_value=Response(200, json=[[{"label": "X", "score": 1.0}]])
        )
        await HFClient().classify("t", model)

    assert route.calls.last.request.headers["Authorization"].startswith("Bearer ")


# ------ LocalNLPClient


def fake_pipe_classify(text):
    return [{"label": "POSITIVE", "score": 0.99}]


# evitar error fake_pipe_classify() takes 0 positional arguments but 1 was given'


@pytest.mark.asyncio
async def test_classify_local(monkeypatch):

    model = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    client = LocalNLPClient()
    monkeypatch.setattr(client, "_get_pipeline", lambda task, model: fake_pipe_classify)
    # client = Objeto que modificamos
    # atributo como string
    # lambda se usa porque get pipeline tambien devuelve un callable (pipe)

    # Basicamente modifica _get_pipeline para que devuelva un callable (fake_pipe)

    # Proxy

    result = await client.classify("great movie", model)
    assert result.success
    assert result.data == {"label": "POSITIVE", "score": 0.99}


def fake_pipe_zero_shot(text, candidate_labels):
    return {"labels": ["clickbait", "factual news"], "scores": [0.79, 0.21]}


@pytest.mark.asyncio
async def test_zero_shot_local(monkeypatch):

    model = "facebook/bart-large-mnli"
    client = LocalNLPClient()
    monkeypatch.setattr(
        client, "_get_pipeline", lambda task, model: fake_pipe_zero_shot
    )
    result = await client.zero_shot(
        "random_headline", model, ["clickbait", "factual news"]
    )

    assert result.success
    assert result.data == {"label": "clickbait", "score": 0.79}


# ------ Manejo de errores


@pytest.mark.asyncio
async def test_classify_error_returns_fail(monkeypatch):
    # Si _get_pipeline falla classify devuelve fail, no revienta.
    # lambda no puede raise (es una sola expresion) asi queusamos un def.
    def boom(task, model):
        raise RuntimeError("modelo no encontrado")

    client = LocalNLPClient()
    monkeypatch.setattr(client, "_get_pipeline", boom)
    result = await client.classify("texto", "modelo-malo")

    assert not result.success
    assert "modelo-malo" in result.error


def test_get_pipeline_caches(monkeypatch):
    # _get_pipeline crea el pipeline UNA vez por (task, model) y lo reutiliza.
    import sys
    import types

    fake_transformers = types.ModuleType("transformers")
    calls = []

    def fake_pipeline(task, model):
        calls.append((task, model))
        return object()  # un pipe falso cualquiera

    fake_transformers.pipeline = fake_pipeline
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    client = LocalNLPClient()
    p1 = client._get_pipeline("text-classification", "m")
    p2 = client._get_pipeline("text-classification", "m")

    assert p1 is p2  # mismo objeto
    assert len(calls) == 1  # solo se creo una vez


# ------ Factoria get_nlp_backend


def test_factory_returns_local(monkeypatch):
    monkeypatch.setattr(settings, "nlp_backend", "local")
    assert isinstance(get_nlp_backend(), LocalNLPClient)


def test_factory_returns_remote(monkeypatch):
    monkeypatch.setattr(settings, "nlp_backend", "remote")
    assert isinstance(get_nlp_backend(), HFClient)


# retry: timeout y 503 se reintentan
# RETRY_BACKOFF = 0 en la instancia solo `para tests`


@pytest.mark.asyncio
async def test_make_request_retries_on_503_then_succeeds():
    # 503 luego 200
    model = "facebook/bart-large-mnli"
    with respx.mock:
        route = respx.post(f"{MODELS_URL}{model}").mock(
            side_effect=[  # Si pasa lista son side_effects, recorre en orden
                Response(503, text="Model is currently loading"),
                Response(200, json=[{"label": "clickbait", "score": 0.9}]),
            ]
        )
        client = HFClient()
        client.RETRY_BACKOFF = 0
        result = await client.zero_shot("h", model, ["clickbait", "factual news"])

    assert result.success
    assert result.data == {"label": "clickbait", "score": 0.9}
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_make_request_retries_on_timeout_then_succeeds():
    # Reintentos tambien para Timeouts
    model = "some/model"
    with respx.mock:
        route = respx.post(f"{MODELS_URL}{model}").mock(
            side_effect=[
                TimeoutException("boom"),
                Response(200, json=[[{"label": "OK", "score": 1.0}]]),
            ]
        )
        client = HFClient()
        client.RETRY_BACKOFF = 0
        result = await client.classify("t", model)

    assert result.success
    assert result.data == {"label": "OK", "score": 1.0}
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_make_request_gives_up_after_max_retries():
    # 503 pero agota intentos.
    model = "some/model"
    with respx.mock:
        route = respx.post(f"{MODELS_URL}{model}").mock(
            return_value=Response(503, text="Model is currently loading")
        )
        client = HFClient()
        client.RETRY_BACKOFF = 0
        result = await client.classify("t", model)

    assert not result.success
    assert "503" in result.error
    assert route.call_count == client.MAX_RETRIES + 1


# Integration


# No poner valores concretos ahora, ya haremos tests de valores, solo revisar que el fomrado del resultado es correcto


@pytest.mark.integration
@pytest.mark.asyncio
async def test_classify_real_contract():
    result = await HFClient().classify(
        "I love this", "cardiffnlp/twitter-roberta-base-sentiment-latest"
    )
    assert result.success
    assert "label" in result.data
    assert "score" in result.data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_zero_shot_real_contract():
    result = await HFClient().zero_shot(
        "You will not believe what happened next",
        "facebook/bart-large-mnli",
        ["clickbait", "factual news"],
    )
    assert result.success
    assert result.data["label"] in {"clickbait", "factual news"}


class FakeSim:
    def __init__(self, v):
        self.v = v

    def item(self):
        return self.v


class FakeModel:
    def __init__(self, sim):
        self._sim = sim

    def encode(self, texts):
        return [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]  # 2 x 1-D x 3 nums

    def similarity(self, a, b):
        return FakeSim(self._sim)


# Necesitamos falsificar el modelo transformer para no llamarlo de verdad en .encode y .similarity


# Como similarity devuelve tensors, tenemos que falsearlos (falseando .item)
@pytest.mark.asyncio
async def test_incoherence_detected_true(monkeypatch):
    detector = IncoherenceDetector()
    sim = 0.2

    monkeypatch.setattr(detector, "_get_model", lambda: FakeModel(sim))
    result = await detector.detect("great movie", "bad movie")
    assert result.success
    assert result.data["incoherent"] is True
    assert result.data["similarity"] == 0.2
    assert result.data["headline"] == "great movie"
    assert result.data["content"] == "bad movie"


@pytest.mark.asyncio
async def test_incoherence_detected_false(monkeypatch):
    detector = IncoherenceDetector()
    sim = 0.7

    monkeypatch.setattr(detector, "_get_model", lambda: FakeModel(sim))
    result = await detector.detect("great movie", "good movie")
    assert result.success
    assert result.data["incoherent"] is False
    assert result.data["similarity"] == 0.7
    assert result.data["headline"] == "great movie"
    assert result.data["content"] == "good movie"


@pytest.mark.asyncio
async def test_detector_error_returns_fail(monkeypatch):
    def boom():
        raise RuntimeError("modelo no encontrado")

    detector = IncoherenceDetector()
    monkeypatch.setattr(detector, "_get_model", boom)
    result = await detector.detect("error", "no movie")

    assert not result.success
    assert "Error inesperado calculando incoherencia" in result.error


# --Léxico


def test_lexical_detector_true():

    headline = "7 reasons to avoid ketchup"

    result = lexical.detect(headline)
    assert result.success
    assert result.data["is_clickbait"] is True
    assert result.data["score"] >= lexical.THRESHOLD

    cats = {m["category"] for m in result.data["matches"]}
    assert "leading_number" in cats
    assert "forward_reference" in cats


def test_lexical_detector_false():

    headline = "Spain wins the 2026 World Cup"

    result = lexical.detect(headline)
    assert result.success
    assert result.data["is_clickbait"] is False
    assert not (result.data["score"] >= lexical.THRESHOLD)


def test_lexical_detector_no_headline():

    headline1 = " "
    headline2 = ""

    result1 = lexical.detect(headline1)
    result2 = lexical.detect(headline2)
    assert not (result1.success) and (not result2.success)


def test_lexical_acronym_no_false_positive():

    # Test de Bug de acrónimos con puntos
    result = lexical.detect(
        "Chinese A.I. Models Close the Gap With Anthropic and OpenAI"
    )
    assert result.success
    cues = {m["cue"] for m in result.data["matches"]}
    assert "i" not in cues
    assert result.data["is_clickbait"] is False


# --Lineal Determinista!!! (Si cambia seed, cambia test)


def test_linear_detector_true():
    headline = "10 amazing things you won't believe"

    result = linear.predict(headline)
    assert result.success
    assert result.data["is_clickbait"] is True
    assert result.data["probability"] > 0.5

    # top_cues
    cues = {name for name, _ in result.data["top_cues"]}
    assert cues  # no vacío
    assert "you" in cues  # el cue de mayor peso actual


def test_linear_detector_false():
    headline = "Spain wins the 2026 World Cup"

    result = linear.predict(headline)
    assert result.success
    assert result.data["is_clickbait"] is False
    assert result.data["probability"] < 0.5


def test_linear_detector_no_headline():
    result1 = linear.predict(" ")
    result2 = linear.predict("")
    assert not result1.success and not result2.success


# --Model cards (R3.9, divulgación de modelos)


def test_model_cards_wellformed():
    required = {
        "signal",
        "model_id",
        "name",
        "task",
        "type",
        "dimension",
        "limitations",
        "backend",
    }
    valid_types = {"interpretable", "híbrido", "opaco"}
    valid_dimensions = {"forma", "engano", "tono"}
    assert isinstance(model_cards.MODEL_CARDS, list) and model_cards.MODEL_CARDS
    for card in model_cards.MODEL_CARDS:
        assert required <= card.keys()
        assert card["type"] in valid_types
        assert card["dimension"] in valid_dimensions
        assert isinstance(card["limitations"], list) and card["limitations"]


def test_model_id_es_id_de_maquina_o_None():
    # `model_id` es lo que se le pasa al backend, así que o es un identificador
    # de la Hub («org/modelo») o es None. Una etiqueta legible colada aquí
    # rompería la carga del modelo, no la divulgación.
    for card in model_cards.MODEL_CARDS:
        model_id = card["model_id"]
        if model_id is None:
            continue  # léxico y lineal: no hay nada que descargar
        assert isinstance(model_id, str) and model_id.strip()
        assert "/" in model_id, f"{card['signal']}: «{model_id}» no parece un id"
        assert model_id == model_id.strip()


@pytest.mark.asyncio
async def test_las_dos_fachadas_usan_el_id_de_la_ficha(monkeypatch):
    """El test que justifica #116: unificar los ids no impide que vuelvan a separarse.

    El id vivía cableado en la tool MCP, en el orquestador REST y en el detector
    de incoherencia, además de en la ficha. Cambiarlo en un sitio dejaba las dos
    fachadas respondiendo con modelos distintos al mismo titular **sin que nada
    fallara**: los dos caminos seguían devolviendo una etiqueta válida.

    Por eso no basta con comprobar que las constantes existen: hay que capturar
    con qué modelo se llama DE VERDAD por cada camino.
    """
    from backend.analysis import orchestrator
    from backend.core.models import ToolResult

    fichas = model_cards.cards_by_signal()

    class _Espia:
        """Registra CADA llamada, no la última por método.

        La primera versión guardaba en un dict con clave `zero_shot`/`classify`.
        Cuando #115 pasó la señal de clickbait de `zero_shot` a `classify`, las
        dos señales que usan `classify` empezaron a pisarse: el test seguía en
        verde comprobando la mitad de lo que decía comprobar.
        """

        def __init__(self):
            self.llamadas = []

        async def zero_shot(self, text, model, labels):
            self.llamadas.append(model)
            return ToolResult.ok({"label": "clickbait", "score": 0.9})

        async def classify(self, text, model):
            self.llamadas.append(model)
            # `Clickbait` es lo que devuelve el modelo dedicado; `dedicated`
            # lo traduce. El doble tiene que hablar como el modelo real, no
            # como el contrato, o no se estaría probando la traducción.
            return ToolResult.ok({"label": "Clickbait", "score": 0.8})

    # --- fachada MCP ---
    espia_mcp = _Espia()
    monkeypatch.setattr(nlp_tool, "get_nlp_backend", lambda: espia_mcp)
    mcp = FastMCP("test")
    nlp_tool.register(mcp)
    await mcp.call_tool("detect_clickbait", {"headline": "Un titular"})
    await mcp.call_tool("analyze_sentiment", {"text": "Un texto"})

    # --- fachada REST ---
    espia_rest = _Espia()
    monkeypatch.setattr(orchestrator, "_api", espia_rest)
    await orchestrator._run_signals("Un titular", None)

    esperado = {
        fichas["detect_clickbait"]["model_id"],
        fichas["analyze_sentiment"]["model_id"],
    }
    assert set(espia_mcp.llamadas) == esperado, "la tool MCP no usa el id de la ficha"
    assert len(espia_mcp.llamadas) == 2, "alguna señal no llamó al backend"
    assert set(espia_rest.llamadas) == esperado, (
        "el orquestador no usa el id de la ficha"
    )

    # El tercero no pasa por el backend NLP: carga su modelo él mismo. Antes
    # decía "all-MiniLM-L6-v2" mientras la ficha decía la ruta completa — dos
    # cadenas distintas que resolvían al mismo sitio, así que la divergencia no
    # rompía nada y podía durar para siempre.
    assert (
        IncoherenceDetector.MODEL == fichas["detect_clickbait_incoherence"]["model_id"]
    )


def test_model_cards_serializable_and_cover_signals():
    # La tool describe_models hace json.dumps → debe serializar sin error.
    dumped = json.dumps(model_cards.MODEL_CARDS)
    for name in ["facebook/bart-large-mnli", "all-MiniLM-L6-v2"]:
        assert name in dumped


@pytest.mark.asyncio
async def test_model_cards_signals_match_registered_tools():
    # El campo ``signal`` es la clave con la que /analyze busca la ficha de cada resultado, así que tiene que ser el nombre EXACTO de la tool MCP.
    mcp = FastMCP("test")
    nlp_tool.register(mcp)
    registered = {tool.name for tool in await mcp.list_tools()}

    carded = {card["signal"] for card in model_cards.MODEL_CARDS}
    assert carded <= registered, f"fichas sin tool: {carded - registered}"
