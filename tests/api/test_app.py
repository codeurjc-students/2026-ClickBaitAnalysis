"""Tests de la capa HTTP (R4).

Aquí NO se prueba la orquestación —eso es `test_analyze.py`— sino lo que añade
FastAPI encima: validación de entrada, delegación, CORS y OpenAPI. Por eso se
sustituyen `analyze` y `check_health` en el namespace de `app`: las rutas los
resuelven como globales del módulo en cada llamada.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api import app as app_mod
from backend.api.app import app
from backend.api.schemas import (
    AnalyzeResponse,
    Dimension,
    DimensionVerdict,
    OverallVerdict,
    SignalResult,
    SignalStatus,
    SignalType,
)
from backend.config.settings import settings

client = TestClient(app)


def _respuesta(headline="Un titular", content=None):
    return AnalyzeResponse(
        headline=headline,
        content=content,
        signals=[
            SignalResult(
                name="detect_clickbait_lexical",
                status=SignalStatus.OK,
                dimension=Dimension.FORMA,
                type=SignalType.INTERPRETABLE,
                is_clickbait=True,
                data={"score": 2, "is_clickbait": True},
            )
        ],
        dimensions=[
            DimensionVerdict(
                dimension=Dimension.FORMA,
                is_clickbait=True,
                contributing=["detect_clickbait_lexical"],
            )
        ],
        verdict=OverallVerdict.CLICKBAIT_DE_FORMA,
    )


@pytest.fixture
def analisis(monkeypatch):
    """Sustituye la orquestación y captura con qué se la llamó."""
    recibido = {}

    async def falso_analyze(request):
        recibido["request"] = request
        return _respuesta(request.headline, request.content)

    monkeypatch.setattr(app_mod, "analyze", falso_analyze)
    return recibido


# ----- POST /analyze -----


def test_analyze_devuelve_la_respuesta_completa(analisis):
    response = client.post("/analyze", json={"headline": "Un titular"})

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["verdict"] == "clickbait_de_forma"
    assert cuerpo["signals"][0]["name"] == "detect_clickbait_lexical"
    # El JSON crudo de la herramienta viaja sin aplanar: alimenta las tarjetas
    # de explicabilidad.
    assert cuerpo["signals"][0]["data"] == {"score": 2, "is_clickbait": True}


def test_analyze_pasa_el_cuerpo_a_la_orquestacion(analisis):
    client.post("/analyze", json={"headline": "Un titular", "content": "El cuerpo"})
    assert analisis["request"].content == "El cuerpo"


def test_sin_content_la_peticion_es_valida(analisis):
    # El cuerpo es opcional: sin él sólo se pierde la dimensión de engaño.
    assert client.post("/analyze", json={"headline": "Un titular"}).status_code == 200
    assert analisis["request"].content is None


@pytest.mark.parametrize("blanco", [" ", "", "\t\n"])
def test_titular_en_blanco_es_422(blanco, analisis):
    # 422 y no un 200 con `sin_datos`: la petición es inválida, no es que el
    # análisis no haya dado resultado.
    assert client.post("/analyze", json={"headline": blanco}).status_code == 422


def test_falta_el_titular_es_422(analisis):
    assert client.post("/analyze", json={}).status_code == 422


def test_el_titular_llega_normalizado(analisis):
    client.post("/analyze", json={"headline": "  Un titular  "})
    assert analisis["request"].headline == "Un titular"


# ----- GET /health -----


def test_health_expone_el_estado_agregado(monkeypatch):
    async def falso_check():
        return {
            "status": "degraded",
            "timestamp": "2026-08-04T00:00:00+00:00",
            "integrations": {"nyt": {"reachable": False, "error": "boom"}},
        }

    monkeypatch.setattr(app_mod, "check_health", falso_check)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


# ----- CORS (R4.7) y OpenAPI (R4.8) -----


def test_cors_permite_el_origen_configurado():
    origen = settings.cors_origins[0]
    response = client.options(
        "/analyze",
        headers={"Origin": origen, "Access-Control-Request-Method": "POST"},
    )
    assert response.headers["access-control-allow-origin"] == origen


def test_cors_rechaza_un_origen_no_declarado():
    response = client.options(
        "/analyze",
        headers={
            "Origin": "http://origen-no-declarado.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_openapi_documenta_las_rutas_y_el_contrato():
    esquema = client.get("/openapi.json").json()

    assert set(esquema["paths"]) == {"/analyze", "/health"}
    # Las descripciones de los Field llegan al esquema: son lo que ve quien
    # consume /docs y lo que hereda el cliente TypeScript generado.
    propiedades = esquema["components"]["schemas"]["SignalResult"]["properties"]
    assert "herramienta MCP" in propiedades["name"]["description"]
