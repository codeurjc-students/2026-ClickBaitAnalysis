"""Tests de la capa HTTP (R4).

Aquí NO se prueba la orquestación —eso es `test_analyze.py`— sino lo que añade
FastAPI encima: validación de entrada, delegación, CORS y OpenAPI. Por eso se
sustituyen `analyze` y `check_health` en el namespace de `app`: las rutas los
resuelven como globales del módulo en cada llamada.
"""

import pytest
from fastapi.testclient import TestClient

from backend.analysis.domain import (
    AnalyzeResponse,
    Dimension,
    DimensionVerdict,
    OverallVerdict,
    SignalResult,
    SignalStatus,
    SignalType,
)
from backend.api import app as app_mod
from backend.api.app import app
from backend.api.export_openapi import DESTINO, contrato
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

    assert set(esquema["paths"]) == {
        "/analyze",
        "/tools",
        "/tools/{name}/execute",
        "/history",
        "/health",
    }
    # Las descripciones de los Field llegan al esquema: son lo que ve quien
    # consume /docs y lo que hereda el cliente TypeScript generado.
    propiedades = esquema["components"]["schemas"]["SignalResult"]["properties"]
    assert "herramienta MCP" in propiedades["name"]["description"]


def test_el_contrato_commiteado_esta_al_dia():
    """`frontend/openapi.json` debe ser el que produce el código de hoy (#126).

    De ese fichero se genera el cliente TypeScript, y una copia rancia NO se
    manifiesta como un fallo: el frontend compila igual contra una forma que ya
    no existe, y el dato llega `undefined` al navegador.

    Se comprueba aquí, y no sólo en el CI, para que salte antes de empujar —en el
    mismo `pytest` que ya se corre—. Cierra el PRIMER eslabón, que el JSON
    refleja los modelos; el segundo, que el `.d.ts` sale de ese JSON, lo cierra
    el job de frontend, que es el que tiene Node.
    """
    # `pytest.fail` y no `assert ... == ...` a propósito: la comparación de dos
    # JSON de 36 kB imprime cientos de líneas de diff que no sirven de nada,
    # porque esto no se arregla editando el fichero sino regenerándolo. Lo útil
    # es la instrucción, no la diferencia.
    if not DESTINO.exists() or DESTINO.read_text(encoding="utf-8") != contrato():
        pytest.fail(
            "`frontend/openapi.json` no coincide con el contrato que produce el "
            "código actual. Se arregla regenerando: "
            "`python -m backend.api.export_openapi`, luego `npm run gen:api` "
            "dentro de `frontend/`, y se commitean las dos salidas."
        )


# ----- Precalentado (#125) -----


def test_por_defecto_no_se_precalienta(monkeypatch):
    """El defecto es lo que protege a los otros 193 tests de volverse lentos.

    Precalentar cuesta ~102 s medidos. Si el defecto fuera `True`, cada
    `TestClient(app)` de la suite cargaría tres modelos, y eso no se nota como
    un fallo: se nota como que los tests «van lentos» y nadie sabe por qué.
    """
    llamadas = []
    monkeypatch.setattr(app_mod, "precalentar", lambda: llamadas.append(1))

    assert settings.preheat_models is False
    with TestClient(app):
        pass
    assert llamadas == []


def test_con_el_flag_encendido_se_precalienta_antes_de_servir(monkeypatch, analisis):
    """Y que ocurre DENTRO del lifespan, no en la primera petición.

    Es la diferencia entre trasladar la espera a uvicorn —que es el objetivo— y
    dejarla donde estaba.
    """
    orden = []

    async def falso_precalentar():
        orden.append("precalienta")
        return {"detect_clickbait_incoherence": 1.23}

    monkeypatch.setattr(settings, "preheat_models", True)
    monkeypatch.setattr(app_mod, "precalentar", falso_precalentar)

    with TestClient(app) as cliente:
        orden.append("sirve")
        cliente.post("/analyze", json={"headline": "Un titular"})

    assert orden == ["precalienta", "sirve"]
