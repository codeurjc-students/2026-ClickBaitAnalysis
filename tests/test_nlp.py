import json

import pytest
import respx  # Usamos en vez de htttp, ya que no hacemos llamadas de verdad, mockeamos
from httpx import Response, TimeoutException

from backend.integrations.nlp.client import HFClient

MODELS_URL = "https://router.huggingface.co/hf-inference/models/"


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
