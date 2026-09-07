"""Pruebas del sondeo de salud.

Hay dos capas y responden preguntas distintas. Las de aquí usan `respx` y no
tocan la red: comprueban que `_probe` **interpreta** bien lo que recibe. La
marcada como `integration`, al final, comprueba que las URLs reales siguen
existiendo — otra pregunta, y por eso se conserva.

Hasta #138 sólo estaba la segunda, así que el CI —que corre
`-m "not integration"`— deseleccionaba la única prueba de `_probe` que había: el
cuerpo de la función no se ejecutaba nunca donde importa, y con él las dos ramas
que deciden si una integración responde.
"""

import httpx
import pytest
import respx

from backend.core.health import PROBES, _aggregate_status, _probe, check_health

URL = "https://ejemplo.invalido/sonda"


def test_aggregate_status_all_ok():
    integrations = {
        "weather": {"reachable": True, "error": None},
        "guardian": {"reachable": True, "error": None},
        "nyt": {"reachable": True, "error": None},
    }
    assert _aggregate_status(integrations) == "ok"


def test_aggregate_status_one_fails():
    integrations = {
        "weather": {"reachable": True, "error": None},
        "guardian": {"reachable": False, "error": "boom"},
        "nyt": {"reachable": True, "error": None},
    }
    assert _aggregate_status(integrations) == "degraded"


def test_aggregate_status_some_fail():
    integrations = {
        "weather": {"reachable": False, "error": "boom"},
        "guardian": {"reachable": False, "error": "boom"},
        "nyt": {"reachable": True, "error": None},
    }
    assert _aggregate_status(integrations) == "degraded"


def test_aggregate_status_all_fail():
    integrations = {
        "weather": {"reachable": False, "error": "boom"},
        "guardian": {"reachable": False, "error": "boom"},
        "nyt": {"reachable": False, "error": "boom"},
    }
    assert _aggregate_status(integrations) == "down"


# ----- `_probe`: qué se considera «responde» -----


@pytest.mark.asyncio
async def test_una_respuesta_correcta_es_alcanzable():
    with respx.mock:
        respx.get(URL).mock(return_value=httpx.Response(200, json={}))

        assert await _probe(URL) == {"reachable": True, "error": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("codigo", [404, 500])
async def test_un_codigo_de_error_no_es_alcanzable(codigo):
    """El `raise_for_status()` es lo que impide tratar un 4xx o un 5xx como
    respuesta aceptable: la API contestó, pero no sirve."""
    with respx.mock:
        respx.get(URL).mock(return_value=httpx.Response(codigo))

        resultado = await _probe(URL)

    assert resultado["reachable"] is False
    assert resultado["error"]


@pytest.mark.asyncio
async def test_un_fallo_de_red_no_es_alcanzable():
    """La otra rama: no hay respuesta que interpretar, no llega la conexión."""
    with respx.mock:
        respx.get(URL).mock(side_effect=httpx.ConnectError("sin ruta al host"))

        resultado = await _probe(URL)

    assert resultado["reachable"] is False
    assert "sin ruta al host" in resultado["error"]


@pytest.mark.asyncio
async def test_los_parametros_viajan_en_la_peticion():
    """Las sondas de Guardian y NYT llevan su clave: sin ella, la API responde
    401 y la integración saldría caída estando viva."""
    with respx.mock:
        ruta = respx.get(URL).mock(return_value=httpx.Response(200, json={}))

        await _probe(URL, {"api-key": "una-clave"})

    assert ruta.calls.last.request.url.params["api-key"] == "una-clave"


# ----- `check_health`: el agregado -----


@pytest.mark.asyncio
async def test_check_health_sondea_todas_y_agrega():
    """Una sola integración caída deja el sistema en `degraded`, no en `down`.

    Y las tres aparecen en el detalle: sin él, un semáforo en ámbar no dice
    CUÁL falla, que es lo único accionable.
    """
    with respx.mock:
        for nombre, configuracion in PROBES.items():
            codigo = 500 if nombre == "guardian" else 200
            respx.get(configuracion["url"]).mock(
                return_value=httpx.Response(codigo, json={})
            )

        salud = await check_health()

    assert salud["status"] == "degraded"
    assert set(salud["integrations"]) == set(PROBES)
    assert salud["integrations"]["guardian"]["reachable"] is False
    assert salud["integrations"]["nyt"]["reachable"] is True
    # La marca de tiempo lleva zona horaria: sin ella, dos despliegues en husos
    # distintos producirían historiales que no se pueden ordenar entre sí.
    assert salud["timestamp"].endswith("+00:00")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(PROBES))
async def test_probe_reaches_api(name):
    result = await _probe(**PROBES[name])
    assert result["reachable"] is True
    assert result["error"] is None
