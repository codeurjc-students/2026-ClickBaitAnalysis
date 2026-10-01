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

import asyncio
import json

import httpx
import pytest
import respx

from backend.config.settings import settings
from backend.core import health
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
    """La otra rama: no hay respuesta que interpretar, no llega la conexión.

    Hasta #163 este test exigía lo contrario de la última línea: que el texto de
    la excepción llegara a la respuesta. Es justo lo que filtraba la clave.
    """
    with respx.mock:
        respx.get(URL).mock(side_effect=httpx.ConnectError("sin ruta al host"))

        resultado = await _probe(URL)

    assert resultado["reachable"] is False
    assert resultado["error"] == "ConnectError"
    assert "sin ruta al host" not in resultado["error"]


@pytest.mark.asyncio
async def test_un_timeout_dice_que_lo_es():
    """Medido el 2026-09-17: `str()` de un timeout de httpx es una cadena VACÍA,
    y el indicador trataba ese error como «sin detalle»."""
    with respx.mock:
        respx.get(URL).mock(side_effect=httpx.ConnectTimeout(""))

        resultado = await _probe(URL)

    assert resultado["error"] == "ConnectTimeout"


# ----- La clave no sale por la respuesta (#163) -----

CLAVE = "clave-de-prueba-7f3a9c"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        (401, "HTTP 401 Unauthorized"),
        (429, "HTTP 429 Too Many Requests"),
        (500, "HTTP 500 Internal Server Error"),
    ],
)
async def test_un_error_http_dice_el_codigo_y_no_la_url(codigo, esperado):
    """El mensaje de httpx para un 4xx o 5xx lleva la URL entera, y Guardian y
    NYT llevan la clave en ella. Con una clave válida esto no desaparece: pasa
    cada vez que la API responde con error, un 429 por cuota incluido."""
    with respx.mock:
        respx.get(URL).mock(return_value=httpx.Response(codigo))

        resultado = await _probe(URL, {"api-key": CLAVE})

    assert resultado["error"] == esperado
    assert CLAVE not in resultado["error"]


@pytest.mark.asyncio
async def test_check_health_no_publica_las_claves_configuradas():
    """La prueba que fija el arreglo, sobre la respuesta ENTERA y con las claves
    de verdad de la configuración: cualquier campo que se añada mañana queda
    cubierto sin tener que acordarse de él."""
    with respx.mock:
        for configuracion in PROBES.values():
            respx.get(configuracion["url"]).mock(return_value=httpx.Response(401))

        salud = json.dumps(await check_health())

    for configuracion in PROBES.values():
        clave = configuracion.get("params", {}).get("api-key")
        if clave:
            assert clave not in salud


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


# ----- La caché del sondeo (#169) -----


class RelojDeMentira:
    """Ocupa el sitio del módulo `time` dentro de `health`.

    Sólo se le pide `monotonic`, así que basta con eso. Se sustituye el atributo
    del módulo y no la función global: un test que retrase el reloj de todo el
    proceso es un test que estropea a los demás.
    """

    def __init__(self) -> None:
        self.ahora = 1_000.0

    def monotonic(self) -> float:
        return self.ahora


def _sondas_que_responden() -> list:
    """Las tres APIs contestando 200. Se llama DENTRO de `respx.mock`."""
    return [
        respx.get(configuracion["url"]).mock(return_value=httpx.Response(200, json={}))
        for configuracion in PROBES.values()
    ]


@pytest.mark.asyncio
async def test_dos_sondeos_seguidos_preguntan_una_sola_vez(monkeypatch):
    """Lo ÚNICO que acota la cuota diaria de NYT (#169).

    El límite de velocidad reparte el abuso entre clientes, pero cien clientes
    distintos agotan las 500 llamadas igual. Esto no depende de cuántos sean.
    """
    monkeypatch.setattr(settings, "health_cache_s", 30.0)
    health.olvidar_sondeo()

    with respx.mock:
        rutas = _sondas_que_responden()
        primera = await check_health()
        segunda = await check_health()

    assert [ruta.call_count for ruta in rutas] == [1, 1, 1]
    # Con el MISMO `timestamp`: una respuesta cacheada dice su propia edad en
    # vez de fingir que se acaba de sondear. Por eso no hizo falta tocar el
    # contrato para que la interfaz pueda decidir si le vale.
    assert segunda["timestamp"] == primera["timestamp"]


@pytest.mark.asyncio
async def test_pasado_el_plazo_vuelve_a_sondear(monkeypatch):
    reloj = RelojDeMentira()
    monkeypatch.setattr(health, "time", reloj)
    monkeypatch.setattr(settings, "health_cache_s", 30.0)
    health.olvidar_sondeo()

    with respx.mock:
        rutas = _sondas_que_responden()
        await check_health()
        reloj.ahora += 31
        await check_health()

    assert [ruta.call_count for ruta in rutas] == [2, 2, 2]


@pytest.mark.asyncio
async def test_diez_peticiones_a_la_vez_sondean_una_sola_vez(monkeypatch):
    """El caso que de verdad dispara la cuota: varias pantallas a la vez.

    Sin el cerrojo, las diez encontrarían la caché vacía antes de que la primera
    terminara y saldrían treinta peticiones externas en lugar de tres.
    """
    monkeypatch.setattr(settings, "health_cache_s", 30.0)
    health.olvidar_sondeo()

    with respx.mock:
        rutas = _sondas_que_responden()
        resultados = await asyncio.gather(*(check_health() for _ in range(10)))

    assert [ruta.call_count for ruta in rutas] == [1, 1, 1]
    assert all(resultado == resultados[0] for resultado in resultados)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(PROBES))
async def test_probe_reaches_api(name):
    result = await _probe(**PROBES[name])
    assert result["reachable"] is True
    assert result["error"] is None
