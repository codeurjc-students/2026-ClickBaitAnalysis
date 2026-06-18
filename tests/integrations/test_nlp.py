import asyncio
import json

import pytest
import respx  # Usamos en vez de htttp, ya que no hacemos llamadas de verdad, mockeamos
from httpx import Response, TimeoutException

from backend.integrations.nlp.client import HFClient
from backend.integrations.nlp.incoherence import IncoherenceDetector
from backend.integrations.nlp.local import LocalNLPClient
from backend.integrations.nlp.factory import get_nlp_backend
from backend.config.settings import settings

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
