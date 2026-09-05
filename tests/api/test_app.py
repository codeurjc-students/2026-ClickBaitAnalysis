"""Tests de la capa HTTP (R4).

Aquí NO se prueba la orquestación —eso es `test_analyze.py`— sino lo que añade
FastAPI encima: validación de entrada, delegación, CORS y OpenAPI. Por eso se
sustituyen `analyze` y `check_health` en el namespace de `app`: las rutas los
resuelven como globales del módulo en cada llamada.
"""

import json

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
                label="Léxico por reglas",
                status=SignalStatus.OK,
                dimension=Dimension.FORM,
                type=SignalType.INTERPRETABLE,
                is_clickbait=True,
                data={"score": 2, "is_clickbait": True},
            )
        ],
        dimensions=[
            DimensionVerdict(
                dimension=Dimension.FORM,
                is_clickbait=True,
                contributing=["detect_clickbait_lexical"],
            )
        ],
        verdict=OverallVerdict.STYLISTIC_CLICKBAIT,
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
    # El análisis viaja ENVUELTO desde #133: el sobre lleva el id del historial
    # al lado, así que lo que antes era la raíz ahora cuelga de `analysis`.
    cuerpo = response.json()["analysis"]
    assert cuerpo["verdict"] == "stylistic_clickbait"
    assert cuerpo["signals"][0]["name"] == "detect_clickbait_lexical"
    # La etiqueta para personas viaja junto al nombre de máquina (#133): sin
    # ella la interfaz mantenía su propio diccionario sin vigilancia.
    assert cuerpo["signals"][0]["label"] == "Léxico por reglas"
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
    # 422 y no un 200 con `no_data`: la petición es inválida, no es que el
    # análisis no haya dado resultado.
    assert client.post("/analyze", json={"headline": blanco}).status_code == 422


def test_falta_el_titular_es_422(analisis):
    assert client.post("/analyze", json={}).status_code == 422


def test_el_titular_llega_normalizado(analisis):
    client.post("/analyze", json={"headline": "  Un titular  "})
    assert analisis["request"].headline == "Un titular"


def test_el_analisis_llega_con_el_id_de_su_entrada(analisis):
    """El id se calculaba desde #102 y se tiraba antes de salir del proceso.

    Sin él no había forma de volver a un análisis concreto, aunque estuviera
    guardado entero: `GET /history` sólo sabe devolver páginas con filtros.
    """
    cuerpo = client.post("/analyze", json={"headline": "Un titular"}).json()

    assert isinstance(cuerpo["id"], int)
    # Y el id sirve de verdad: apunta a la entrada que se acaba de escribir.
    entrada = client.get(f"/history/{cuerpo['id']}").json()
    assert entrada["headline"] == "Un titular"


def test_si_el_registro_falla_el_analisis_se_devuelve_igual(analisis, monkeypatch):
    """Ésta es la razón de que `id` sea opcional, y no un detalle de estilo.

    `record()` devuelve None cuando no puede guardar, porque perder un análisis
    correcto por un disco lleno sería peor que no guardarlo. Si la respuesta
    exigiera el id, ese fallo silencioso pasaría a ser un 500.
    """

    async def no_guarda(**kwargs):
        return None

    monkeypatch.setattr(app_mod.history, "record", no_guarda)

    response = client.post("/analyze", json={"headline": "Un titular"})

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["id"] is None
    assert cuerpo["analysis"]["verdict"] == "stylistic_clickbait"


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
        "/history/{entry_id}",
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


def test_ninguna_referencia_del_contrato_queda_colgando():
    """Todo `$ref` del documento apunta a un esquema que existe.

    Lo vigila porque #133 empezó a publicar las formas del `data` a mano, y
    Pydantic genera los tipos anidados en un `$defs` LOCAL: copiarlos sin más
    dejaría `SalidaLexica.matches` apuntando a `#/$defs/Pista`, que en un
    documento OpenAPI no resuelve.

    Y el fallo no se vería. `openapi-typescript` no revienta con una referencia
    rota: genera `unknown`, el frontend compila, y el tipo simplemente deja de
    comprobar nada — que es la forma exacta de fallo que el contrato generado
    existe para evitar.
    """
    documento = json.loads(contrato())
    esquemas = documento["components"]["schemas"]
    prefijo = "#/components/schemas/"

    def referencias(nodo):
        if isinstance(nodo, dict):
            for clave, valor in nodo.items():
                if clave == "$ref":
                    yield valor
                else:
                    yield from referencias(valor)
        elif isinstance(nodo, list):
            for elemento in nodo:
                yield from referencias(elemento)

    rotas = [
        ref
        for ref in referencias(documento)
        if not ref.startswith(prefijo) or ref[len(prefijo) :] not in esquemas
    ]
    assert not rotas, f"Referencias que no resuelven: {sorted(set(rotas))}"


def test_las_formas_del_data_se_publican_como_esquemas():
    """El `data` sigue sin tipo, pero sus formas conocidas ya no se copian a mano.

    Antes de #133 vivían dos veces —`outputs.py` en Python y cuatro interfaces
    escritas a mano en `datos.ts`— sin ningún vínculo entre ellas.
    """
    esquemas = json.loads(contrato())["components"]["schemas"]

    for nombre in ("Etiqueta", "SalidaLexica", "SalidaLineal", "SalidaIncoherencia"):
        assert nombre in esquemas

    # El umbral viaja con el resultado de la señal híbrida: sin él, `incoherent`
    # es un veredicto que hay que creerse.
    assert "threshold" in esquemas["SalidaIncoherencia"]["properties"]


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
