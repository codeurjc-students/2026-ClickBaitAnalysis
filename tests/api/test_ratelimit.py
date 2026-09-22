"""Tests del límite de velocidad de las peticiones entrantes (R12.4, #169).

**Ninguno duerme.** El criterio de la issue lo pide explícitamente, y no es
manía: comprobar que una ventana de un minuto se vacía esperando un minuto
convierte la suite en algo que ya nadie ejecuta en cada cambio. Por eso
`Limitador` recibe su reloj, y aquí se le da uno que sólo avanza cuando se lo
mandan.

Hay dos capas, y responden preguntas distintas. La de arriba prueba la cuenta
—cuántas caben, cuánto hay que esperar, quién es quién— sin HTTP de por medio.
La de abajo prueba lo que sólo se ve a través de la aplicación montada: qué
código sale, qué cabeceras lleva y que las rutas baratas no caen con las caras.
"""

import pytest
from fastapi.testclient import TestClient

from backend.analysis.domain import AnalyzeResponse, OverallVerdict
from backend.api import app as app_mod
from backend.api import ratelimit
from backend.api.app import app
from backend.api.ratelimit import CARAS, RESTO, SONDEO, Limitador, Presupuesto
from backend.config.settings import settings


class Cronometro:
    """Un reloj que sólo avanza cuando se lo mandan."""

    def __init__(self) -> None:
        self.ahora = 1_000.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


# ----- La cuenta -----


def test_pasan_las_del_presupuesto_y_la_siguiente_tiene_que_esperar():
    limitador = Limitador({RESTO: Presupuesto(3, 60.0)}, reloj=Cronometro())

    admitidas = [limitador.consumir("10.0.0.1", RESTO) for _ in range(3)]

    assert admitidas == [None, None, None]
    assert limitador.consumir("10.0.0.1", RESTO) == pytest.approx(60.0)


def test_la_espera_es_hasta_que_caduca_la_mas_vieja():
    """Lo que hace exacto el `Retry-After`, y la razón de la ventana deslizante.

    Con un cubo de fichas el número sería una estimación del ritmo de recarga;
    aquí es el instante en que vuelve a haber sitio de verdad.
    """
    cronometro = Cronometro()
    limitador = Limitador({RESTO: Presupuesto(2, 60.0)}, reloj=cronometro)

    limitador.consumir("10.0.0.1", RESTO)
    cronometro.avanzar(10)
    limitador.consumir("10.0.0.1", RESTO)
    cronometro.avanzar(5)

    assert limitador.consumir("10.0.0.1", RESTO) == pytest.approx(45.0)


def test_al_salir_de_la_ventana_vuelve_a_caber():
    cronometro = Cronometro()
    limitador = Limitador({RESTO: Presupuesto(2, 60.0)}, reloj=cronometro)

    limitador.consumir("10.0.0.1", RESTO)
    limitador.consumir("10.0.0.1", RESTO)
    assert limitador.consumir("10.0.0.1", RESTO) is not None

    cronometro.avanzar(60.1)

    assert limitador.consumir("10.0.0.1", RESTO) is None


def test_cada_cliente_lleva_su_cuenta():
    """El criterio de #169: se limita al cliente, no al proxy entero."""
    limitador = Limitador({RESTO: Presupuesto(1, 60.0)}, reloj=Cronometro())

    assert limitador.consumir("10.0.0.1", RESTO) is None
    assert limitador.consumir("10.0.0.1", RESTO) is not None
    assert limitador.consumir("10.0.0.2", RESTO) is None


def test_cada_grupo_lleva_su_cuenta():
    """Agotar lo caro no puede dejar sin nada a lo barato."""
    limitador = Limitador(
        {CARAS: Presupuesto(1, 60.0), RESTO: Presupuesto(3, 60.0)},
        reloj=Cronometro(),
    )

    limitador.consumir("10.0.0.1", CARAS)

    assert limitador.consumir("10.0.0.1", CARAS) is not None
    assert limitador.consumir("10.0.0.1", RESTO) is None


def test_olvida_a_los_clientes_que_dejaron_de_venir():
    """Sin poda, el diccionario crece con cada IP que pase por delante."""
    cronometro = Cronometro()
    limitador = Limitador(
        {RESTO: Presupuesto(5, 60.0)}, reloj=cronometro, podar_desde=3
    )

    for numero in range(3):
        limitador.consumir(f"10.0.0.{numero}", RESTO)
    assert limitador.seguidos == 3

    cronometro.avanzar(61)
    limitador.consumir("10.0.0.99", RESTO)

    assert limitador.seguidos == 1


@pytest.mark.parametrize(
    ("metodo", "ruta", "esperado"),
    [
        ("POST", "/analyze", CARAS),
        ("POST", "/tools/detect_clickbait/execute", CARAS),
        ("GET", "/health", SONDEO),
        ("GET", "/tools", RESTO),
        ("GET", "/history", RESTO),
        ("GET", "/history/7", RESTO),
        # Exenta: la comprobación previa de CORS la hace el navegador solo y no
        # cuesta nada. Un 429 ahí llegaría a la pantalla como un fallo de CORS,
        # o sea, como «no hay API» — el diagnóstico equivocado.
        ("OPTIONS", "/analyze", None),
    ],
)
def test_cada_ruta_cae_en_su_grupo(metodo, ruta, esperado):
    assert ratelimit.grupo_de(metodo, ruta) == esperado


# ----- A través de la aplicación -----

cliente = TestClient(app, client=("10.0.0.1", 40000))
otro_cliente = TestClient(app, client=("10.0.0.2", 40000))


@pytest.fixture
def limite(monkeypatch):
    """Enciende el limitador con presupuestos diminutos.

    Encendido, porque la suite entera lo apaga (ver `tests/conftest.py`), y
    diminutos para no hacer sesenta peticiones por test.
    """
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_analyze", 2)
    monkeypatch.setattr(settings, "rate_limit_health", 2)
    monkeypatch.setattr(settings, "rate_limit_default", 3)
    ratelimit.reiniciar_limitador()
    yield
    ratelimit.reiniciar_limitador()


@pytest.fixture
def analisis(monkeypatch):
    """Sustituye la orquestación: aquí no se prueba analizar, sino contar."""

    async def falso_analyze(request):
        return AnalyzeResponse(
            headline=request.headline,
            content=None,
            signals=[],
            dimensions=[],
            verdict=OverallVerdict.NO_DATA,
        )

    monkeypatch.setattr(app_mod, "analyze", falso_analyze)


def test_al_pasarse_responde_429_diciendo_cuanto_esperar(limite):
    for _ in range(3):
        assert cliente.get("/history").status_code == 200

    respuesta = cliente.get("/history")

    assert respuesta.status_code == 429
    assert int(respuesta.headers["Retry-After"]) >= 1
    assert "Vuelve a intentarlo" in respuesta.json()["detail"]


def test_las_rutas_baratas_no_caen_con_las_caras(limite, analisis):
    """El tercer criterio de #169, y el motivo de que haya tres presupuestos."""
    for _ in range(2):
        assert (
            cliente.post("/analyze", json={"headline": "Un titular"}).status_code == 200
        )

    agotada = cliente.post("/analyze", json={"headline": "Un titular"})

    assert agotada.status_code == 429
    assert cliente.get("/history").status_code == 200


def test_cada_cliente_tiene_su_cupo_tambien_por_http(limite):
    for _ in range(3):
        cliente.get("/history")
    assert cliente.get("/history").status_code == 429

    assert otro_cliente.get("/history").status_code == 200


def test_el_429_sale_con_las_cabeceras_de_cors(limite):
    """Lo que decide el ORDEN en que se registran los middlewares.

    Con el limitador por fuera del de CORS, esta respuesta no llevaría
    `Access-Control-Allow-Origin`: el navegador la daría por bloqueada y la
    pantalla diría «no se pudo contactar con la API» en vez del límite. Y sin
    `expose-headers`, el JavaScript vería el 429 pero no cuánto esperar.
    """
    cabeceras = {"Origin": settings.cors_origins[0]}
    for _ in range(3):
        cliente.get("/history", headers=cabeceras)

    respuesta = cliente.get("/history", headers=cabeceras)

    assert respuesta.status_code == 429
    assert respuesta.headers["access-control-allow-origin"] == settings.cors_origins[0]
    assert "Retry-After" in respuesta.headers["access-control-expose-headers"]


def test_la_comprobacion_previa_de_cors_no_gasta_presupuesto(limite, analisis):
    """Doble red: el middleware de CORS responde al *preflight* antes de que
    llegue aquí, y aun así `grupo_de` lo exime. Las dos cosas dicen lo mismo a
    propósito — la segunda deja de ser redundante el día que alguien cambie el
    orden de los middlewares."""
    preflight = {
        "Origin": settings.cors_origins[0],
        "Access-Control-Request-Method": "POST",
    }
    for _ in range(5):
        assert cliente.options("/analyze", headers=preflight).status_code == 200

    assert cliente.post("/analyze", json={"headline": "Un titular"}).status_code == 200


def test_todas_las_rutas_declaran_el_429():
    """El contrato tiene que decirlo en TODAS, porque ninguna está exenta.

    Se declara una sola vez, en el constructor de `FastAPI`, y por eso lo que
    hay que vigilar no es que alguien se olvide en una ruta nueva —ya no puede—
    sino que nadie quite esa declaración global.
    """
    operaciones = [
        operacion
        for metodos in app.openapi()["paths"].values()
        for operacion in metodos.values()
    ]

    assert operaciones
    for operacion in operaciones:
        assert "429" in operacion["responses"], operacion["summary"]


def test_apagado_no_limita_nada(monkeypatch):
    """Lo que hace que el resto de la suite no tenga que saber de esto."""
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    ratelimit.reiniciar_limitador()

    for _ in range(10):
        assert cliente.get("/history").status_code == 200
