"""Tests del historial.

Dos bloques, porque responden preguntas distintas:

- **El almacén** (`backend.api.history`), llamando a sus funciones: si los datos
  sobreviven, si salen en orden y si un fallo de escritura se queda donde debe.
- **El endpoint** (`GET /history`), por HTTP: si la decisión de fondo —«una
  entrada por análisis, no una por herramienta invocada»— se sostiene de verdad.

Los tests del almacén usan `asyncio.run()` en vez del marcador de pytest-asyncio
porque `pytest.ini` no declara `asyncio_mode = auto`: la alternativa sería
marcar cada uno a mano para ganar lo mismo.

La base de datos de cada test es un fichero nuevo bajo `tmp_path`, gracias al
fixture `_historial_aislado` de `tests/conftest.py`. Ningún test hereda entradas
de otro ni deja rastro en `var/`.
"""

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta, timezone

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
from backend.api import history
from backend.api.app import app
from backend.api.schemas import (
    ExecuteResponse,
    ExecuteStatus,
    HistoryKind,
    Origin,
)
from backend.config.settings import settings
from backend.core.mcp.tools import ToolNotFound

client = TestClient(app)


def _guardar(**cambios) -> int | None:
    """`record` con los obligatorios ya puestos, para no repetirlos en cada test."""
    argumentos = {
        "kind": HistoryKind.ANALYSIS,
        "origin": Origin.API,
        "status": "ok",
        "payload": {"verdict": "factual"},
        **cambios,
    }
    return asyncio.run(history.record(**argumentos))


def _leer(limit=20, offset=0):
    return asyncio.run(history.query(limit, offset))


# ---------------------------------------------------------------- el almacén


def test_guarda_y_recupera():
    identificador = _guardar(headline="Un titular", verdict="factual")
    assert identificador == 1  # primera fila, AUTOINCREMENT empieza en 1

    filas, total = _leer()
    assert total == 1
    assert filas[0]["headline"] == "Un titular"
    assert filas[0]["verdict"] == "factual"
    assert filas[0]["kind"] == "analysis"


def test_el_payload_vuelve_como_diccionario():
    """La garantía de aislamiento: entra un diccionario, sale un diccionario.

    Si saliera como cadena, quien llame tendría que hacer `json.loads` — es decir,
    tendría que saber que aquí dentro se guarda serializado. Con Postgres y una
    columna `jsonb` ese `json.loads` de fuera reventaría.
    """
    _guardar(payload={"verdict": "deceptive", "signals": [{"name": "lexical"}]})

    filas, _ = _leer()
    assert filas[0]["payload"] == {
        "verdict": "deceptive",
        "signals": [{"name": "lexical"}],
    }


def test_crea_el_directorio_si_no_existe(tmp_path, monkeypatch):
    """Recién clonado el repo, `var/` no existe: está en .gitignore."""
    destino = tmp_path / "no" / "existe" / "todavia" / "history.db"
    monkeypatch.setattr(settings, "history_db", str(destino))

    assert _guardar() == 1
    assert destino.exists()


def test_una_ruta_relativa_se_ancla_a_la_raiz_del_repo(monkeypatch):
    """Sin esto, arrancar uvicorn desde otro directorio crearía una segunda base
    de datos vacía, y el síntoma sería «se ha borrado el historial»."""
    monkeypatch.setattr(settings, "history_db", "var/history.db")

    ruta = history._ruta_db()
    assert ruta.is_absolute()
    assert ruta == history._RAIZ / "var" / "history.db"


def test_una_ruta_absoluta_se_respeta(monkeypatch, tmp_path):
    """Es lo que se configurará en el contenedor con HISTORY_DB=/var/lib/..."""
    destino = tmp_path / "en" / "otro" / "sitio.db"
    monkeypatch.setattr(settings, "history_db", str(destino))

    assert history._ruta_db() == destino


def test_las_entradas_salen_de_la_mas_nueva_a_la_mas_vieja():
    for titular in ("primero", "segundo", "tercero"):
        _guardar(headline=titular)

    filas, _ = _leer()
    assert [f["headline"] for f in filas] == ["tercero", "segundo", "primero"]


def test_la_paginacion_devuelve_el_total_completo():
    for i in range(5):
        _guardar(headline=f"titular {i}")

    filas, total = _leer(limit=2, offset=2)
    assert len(filas) == 2
    # El total es de TODAS las entradas, no de la página: es lo que la interfaz
    # necesita para pintar «3-4 de 5».
    assert total == 5
    assert [f["headline"] for f in filas] == ["titular 2", "titular 1"]


def test_un_fallo_de_escritura_no_propaga(monkeypatch):
    """El análisis ya se hizo y es correcto: perderlo porque el disco esté lleno
    sería peor que no guardarlo. Devuelve None y deja el motivo en el log."""

    def revienta(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(history, "_guardar", revienta)

    assert _guardar() is None


def test_conectar_cierra_la_conexion_al_salir():
    """El `with` de sqlite3 gestiona la TRANSACCIÓN, no el cierre.

    Sin el `close()` explícito, cerrarla queda en manos del recolector: medido,
    20 000 escrituras dejaban hasta 163 descriptores abiertos hasta el siguiente
    `gc.collect()`. Operar sobre una conexión ya cerrada lanza ProgrammingError.
    """
    with history._conectar() as conexion:
        conexion.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError):
        conexion.execute("SELECT 1")


def test_una_excepcion_deshace_la_escritura():
    """La otra mitad del gestor de contexto: rollback si algo revienta dentro.

    Y prueba de paso que el orden es el correcto — confirmar ANTES de cerrar. Si
    fuera al revés, cerrar con una transacción pendiente la desharía siempre.
    """
    with pytest.raises(RuntimeError):
        with history._conectar() as conexion:
            conexion.execute(
                history._INSERT,
                (
                    "2026-01-01T00:00:00+00:00",
                    "analysis",
                    "api",
                    "x",
                    None,
                    None,
                    "ok",
                    "{}",
                ),
            )
            raise RuntimeError("boom")

    _, total = _leer()
    assert total == 0


# ---------------------------------------------------------------- la retención


def _sembrar(cuantas, dias=0):
    """Escribe filas saltándose la poda, para preparar un estado de partida."""
    marca = (datetime.now(UTC) - timedelta(days=dias)).isoformat()
    with history._conectar() as conexion:
        conexion.executemany(
            history._INSERT,
            [
                (marca, "analysis", "api", f"t{i}", None, "factual", "ok", "{}")
                for i in range(cuantas)
            ],
        )


def test_la_poda_por_cantidad_no_borra_si_no_sobra(monkeypatch):
    """Desde ABAJO: con menos filas que el techo no sobra nada, así que no se
    toca ni una. Es la mitad de corrección del criterio — una poda que borra por
    debajo del límite destruye datos que la política dice conservar."""
    monkeypatch.setattr(settings, "history_max_entries", 1000)
    monkeypatch.setattr(settings, "history_max_days", 0)
    _sembrar(500)

    _guardar()

    _, total = _leer()
    assert total == 501


def test_la_poda_por_cantidad_recorta_al_techo(monkeypatch):
    """Desde ARRIBA, y en UNA sola escritura.

    Es el escenario del despliegue, no un caso teórico: el historial lleva
    creciendo sin techo desde que se añadió la persistencia, así que al activar
    la retención lo primero que se encuentra es una tabla por encima del límite.
    Que la poda reduzca —y no sólo mantenga— es lo que evita una migración.
    """
    monkeypatch.setattr(settings, "history_max_entries", 100)
    monkeypatch.setattr(settings, "history_max_days", 0)
    _sembrar(3000)

    _guardar(headline="el que dispara la poda")

    filas, total = _leer(limit=1)
    assert total == 100
    assert filas[0]["headline"] == "el que dispara la poda"


def test_la_poda_por_antiguedad_respeta_lo_reciente(monkeypatch):
    monkeypatch.setattr(settings, "history_max_entries", 0)
    monkeypatch.setattr(settings, "history_max_days", 30)
    _sembrar(10, dias=60)  # caducadas
    _sembrar(5, dias=2)  # dentro del plazo

    _guardar()

    _, total = _leer()
    assert total == 6  # las 5 recientes + la que acaba de entrar


def test_cero_desactiva_la_retencion(monkeypatch):
    """En desarrollo interesa no perder las pruebas propias entre sesiones."""
    monkeypatch.setattr(settings, "history_max_entries", 0)
    monkeypatch.setattr(settings, "history_max_days", 0)
    _sembrar(50, dias=900)

    _guardar()

    _, total = _leer()
    assert total == 51


def test_el_indice_de_fecha_existe():
    """Sin él, `created_at < ?` recorre la tabla entera: 2374 µs contra 0,99 µs
    sobre 1000 filas, y la diferencia crece con el tamaño."""
    with history._conectar() as conexion:
        indices = {
            fila["name"]
            for fila in conexion.execute("PRAGMA index_list(history)").fetchall()
        }

    assert "idx_history_created_at" in indices


# ---------------------------------------------------------------- el endpoint


def _respuesta_analisis(headline="Un titular"):
    return AnalyzeResponse(
        headline=headline,
        content=None,
        signals=[
            SignalResult(
                name="detect_clickbait_lexical",
                label="Léxico por reglas",
                status=SignalStatus.OK,
                dimension=Dimension.FORM,
                type=SignalType.INTERPRETABLE,
                is_clickbait=True,
                data={"score": 2},
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
    async def falso_analyze(request):
        return _respuesta_analisis(request.headline)

    monkeypatch.setattr(app_mod, "analyze", falso_analyze)


@pytest.fixture
def ejecucion(monkeypatch):
    async def falso_execute(name, arguments):
        return ExecuteResponse(
            tool=name,
            server="http://127.0.0.1:8765/mcp",
            status=ExecuteStatus.OK,
            data={"score": 2},
        )

    monkeypatch.setattr(app_mod, "execute_tool", falso_execute)


def test_historial_vacio():
    cuerpo = client.get("/history").json()

    assert cuerpo["items"] == []
    assert cuerpo["total"] == 0
    assert cuerpo["limit"] == 20


def test_un_analyze_deja_UNA_entrada_y_no_una_por_senal(analisis):
    """La decisión de fondo del historial.

    Un `/analyze` invoca cinco herramientas. Guardarlas sueltas daría una lista
    de `detect_clickbait_lexical` repetido en vez del titular que el usuario
    analizó. La traza por invocación ya vive en los logs, que es su sitio.
    """
    client.post("/analyze", json={"headline": "Un titular"})

    cuerpo = client.get("/history").json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["kind"] == "analysis"
    assert cuerpo["items"][0]["headline"] == "Un titular"
    assert cuerpo["items"][0]["verdict"] == "stylistic_clickbait"


def test_la_entrada_guarda_la_respuesta_completa(analisis):
    """Es lo que permite volver a mostrar el resultado sin reejecutar — que
    además de costar ~20 s podría dar otro resultado."""
    client.post("/analyze", json={"headline": "Un titular"})

    payload = client.get("/history").json()["items"][0]["payload"]
    assert payload["verdict"] == "stylistic_clickbait"
    assert payload["signals"][0]["name"] == "detect_clickbait_lexical"
    assert payload["signals"][0]["data"] == {"score": 2}


def test_una_ejecucion_suelta_guarda_su_titular(ejecucion):
    """Las señales reciben el titular como argumento: sacarlo de ahí hace que la
    entrada se vea en la lista con su titular en vez de con un hueco."""
    client.post(
        "/tools/detect_clickbait_lexical/execute",
        json={"arguments": {"headline": "Otro titular"}},
    )

    entrada = client.get("/history").json()["items"][0]
    assert entrada["kind"] == "tool"
    assert entrada["tool"] == "detect_clickbait_lexical"
    assert entrada["headline"] == "Otro titular"


def test_una_herramienta_sin_titular_lo_deja_vacio(ejecucion):
    client.post("/tools/health_check/execute", json={"arguments": {}})

    entrada = client.get("/history").json()["items"][0]
    assert entrada["tool"] == "health_check"
    assert entrada["headline"] is None


def test_una_peticion_rechazada_no_se_registra(monkeypatch):
    """Un 404 no es una ejecución: ensuciaría el historial con intentos fallidos
    del formulario en vez de con análisis hechos."""

    async def no_existe(name, arguments):
        raise ToolNotFound(name)

    monkeypatch.setattr(app_mod, "execute_tool", no_existe)

    assert (
        client.post("/tools/inventada/execute", json={"arguments": {}}).status_code
        == 404
    )
    assert client.get("/history").json()["total"] == 0


def test_la_pagina_respeta_limit_y_offset(analisis):
    for i in range(5):
        client.post("/analyze", json={"headline": f"titular {i}"})

    cuerpo = client.get("/history?limit=2&offset=1").json()
    assert cuerpo["total"] == 5
    assert cuerpo["limit"] == 2
    assert cuerpo["offset"] == 1
    assert [i["headline"] for i in cuerpo["items"]] == ["titular 3", "titular 2"]


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_limit_fuera_de_rango_es_422(limit):
    """El tope se valida en la firma, así que sale publicado en OpenAPI y pedir
    de más devuelve 422 en vez de servir otra cosa en silencio.

    El mínimo de 1 no es cosmético: en SQLite un LIMIT NEGATIVO significa «sin
    límite», así que `?limit=-1` traería la tabla entera a memoria.
    """
    assert client.get(f"/history?limit={limit}").status_code == 422


def test_offset_negativo_es_422():
    assert client.get("/history?offset=-1").status_code == 422


def test_los_topes_salen_en_el_esquema_openapi():
    """Lo que justifica validar en la firma en vez de recortar a mano: el cliente
    Angular se genera de aquí, y un tope no publicado se descubre a sorpresas."""
    esquema = client.get("/openapi.json").json()
    parametros = {
        p["name"]: p["schema"]
        for p in esquema["paths"]["/history"]["get"]["parameters"]
    }

    assert parametros["limit"]["maximum"] == 100
    assert parametros["limit"]["minimum"] == 1
    assert parametros["offset"]["minimum"] == 0


def test_una_entrada_se_recupera_por_su_id(analisis):
    """La puerta que le faltaba al historial (#133).

    Lo guardado desde #102 es la respuesta COMPLETA, no un resumen, así que
    recuperar un análisis no obliga a reejecutarlo — que además de costar ~20 s
    podría dar otro resultado, porque las señales remotas no son deterministas.
    """
    creado = client.post("/analyze", json={"headline": "Un titular"}).json()

    entrada = client.get(f"/history/{creado['id']}").json()

    assert entrada["id"] == creado["id"]
    assert entrada["headline"] == "Un titular"
    assert entrada["payload"] == creado["analysis"]


def test_un_id_que_no_existe_da_404():
    """404 y no lista vacía: preguntar por UNA entrada concreta que no está es
    un caso distinto de filtrar y no encontrar nada."""
    assert client.get("/history/999999").status_code == 404


def test_el_contrato_declara_ese_404():
    """Que lo lance no basta: tiene que estar PUBLICADO (#129).

    El cliente de Angular se genera del contrato, así que un código que sólo
    vive en el `raise` obliga a leer `app.py` para saber que existe. Y este en
    concreto no es raro: la retención poda entradas, de modo que un enlace
    guardado a un análisis termina dando 404 por funcionamiento normal.
    """
    respuestas = client.get("/openapi.json").json()["paths"]["/history/{entry_id}"][
        "get"
    ]["responses"]

    assert "404" in respuestas
    assert "entrada" in respuestas["404"]["description"]


def test_un_id_que_no_es_entero_da_422():
    """Lo para la firma, antes de tocar la base de datos."""
    assert client.get("/history/no-soy-un-id").status_code == 422


# ---------------------------------------------------------------- los filtros


def _poblar():
    """Un historial variado: análisis con tres veredictos y dos herramientas."""
    _guardar(headline="engañoso", verdict="deceptive", status="ok")
    _guardar(headline="factual", verdict="factual", status="ok")
    _guardar(headline="roto", verdict="no_data", status="error")
    _guardar(kind=HistoryKind.TOOL, tool="analyze_sentiment", status="ok")
    _guardar(kind=HistoryKind.TOOL, tool="health_check", status="error")


def test_filtro_por_kind():
    """La pestaña «Análisis» / «Herramientas» de la pantalla."""
    _poblar()

    cuerpo = client.get("/history?kind=analysis").json()
    assert cuerpo["total"] == 3
    assert {i["kind"] for i in cuerpo["items"]} == {"analysis"}


def test_filtro_por_tool_solo_alcanza_ejecuciones_sueltas():
    """El desajuste de R9.4, resuelto: un análisis invocó CINCO herramientas, así
    que no hay una por la que filtrarlo y su columna `tool` es nula. La pantalla
    lo hace evidente enseñando el desplegable sólo dentro de «Herramientas»."""
    _poblar()

    cuerpo = client.get("/history?tool=analyze_sentiment").json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["kind"] == "tool"


def test_filtro_por_verdict():
    """Lo que CONCLUYÓ: es el filtro que quiere quien mira sus análisis."""
    _poblar()

    cuerpo = client.get("/history?verdict=deceptive").json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["headline"] == "engañoso"


def test_filtro_por_status_es_el_operativo():
    """Si funcionó la MAQUINARIA. Cruza los dos tipos de entrada, y por eso no
    podía ser el mismo parámetro que el veredicto."""
    _poblar()

    cuerpo = client.get("/history?status=error").json()
    assert cuerpo["total"] == 2
    assert {i["kind"] for i in cuerpo["items"]} == {"analysis", "tool"}


def test_los_filtros_se_acumulan():
    _poblar()

    cuerpo = client.get("/history?kind=analysis&status=ok").json()
    assert cuerpo["total"] == 2
    assert {i["verdict"] for i in cuerpo["items"]} == {"deceptive", "factual"}


def test_el_total_va_ya_filtrado():
    """Sin esto la interfaz pintaría «1-1 de 5» sobre una lista de uno."""
    _poblar()

    cuerpo = client.get("/history?verdict=factual").json()
    assert cuerpo["total"] == 1
    assert len(cuerpo["items"]) == 1


def test_filtro_por_fechas():
    _sembrar(4, dias=60)
    _guardar(headline="de hoy")

    desde = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    cuerpo = client.get("/history", params={"since": desde}).json()

    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["headline"] == "de hoy"


def test_las_fechas_se_normalizan_a_utc():
    """`created_at` se compara entre CADENAS, y eso sólo ordena bien si todas
    llevan el mismo huso: `10:00+02:00` es alfabéticamente menor que `09:00+00:00`
    aunque sea el mismo instante. Sin normalizar, el filtro fallaría en silencio."""
    _guardar(headline="de hoy")

    # El MISMO instante expresado en dos husos distintos: mismo resultado.
    hace_una_hora = datetime.now(UTC) - timedelta(hours=1)
    en_utc = hace_una_hora.isoformat()
    en_otro_huso = hace_una_hora.astimezone(timezone(timedelta(hours=5))).isoformat()

    assert client.get("/history", params={"since": en_utc}).json()["total"] == 1
    assert client.get("/history", params={"since": en_otro_huso}).json()["total"] == 1


def test_el_desfase_horario_hay_que_codificarlo_en_la_url():
    """Documenta una trampa que no es de la API pero cuesta una tarde.

    En una cadena de consulta, `+` significa ESPACIO. Así que un desfase escrito
    a pelo (`...09:00:00+00:00`) llega como `...09:00:00 00:00` y no parsea. No
    afecta a un cliente que codifique sus parámetros —Angular lo hace— pero sí a
    quien teclee la URL. La forma con sufijo `Z` no tiene ese problema.
    """
    _guardar()

    a_pelo = "/history?since=2020-01-01T00:00:00+00:00"
    assert client.get(a_pelo).status_code == 422

    assert client.get("/history?since=2020-01-01T00:00:00Z").status_code == 200
    assert (
        client.get(
            "/history", params={"since": "2020-01-01T00:00:00+00:00"}
        ).status_code
        == 200
    )


def test_un_payload_corrupto_falla_diciendo_que_fila():
    """Ninguna ruta del código puede producirlo: `_guardar` es el único sitio que
    escribe `payload` y siempre con `json.dumps`. Sólo salta editando la base a
    mano — y entonces conviene que diga CUÁL, porque un JSONDecodeError pelado no
    identifica la entrada entre mil."""
    _guardar()
    with history._conectar() as conexion:
        conexion.execute("UPDATE history SET payload = 'esto no es json'")

    with pytest.raises(ValueError, match="entrada 1"):
        _leer()


def test_lo_escrito_y_lo_filtrado_usan_el_mismo_formato_de_fecha():
    """La comparación de `created_at` es entre CADENAS, así que sólo reproduce el
    orden cronológico si todo se escribe igual. Que pase por `_marca` es lo que
    lo garantiza sin depender de que tres sitios se acuerden."""
    _guardar()

    filas, _ = _leer()
    guardado = filas[0]["created_at"]

    assert guardado.endswith("+00:00")  # nunca sufijo `Z`: ordena distinto
    assert guardado == history._marca(datetime.fromisoformat(guardado))


def test_un_kind_inventado_es_422():
    """Al tiparlo como enum, FastAPI lo valida y publica los valores admitidos."""
    assert client.get("/history?kind=inventado").status_code == 422


def test_la_respuesta_declara_la_politica_de_retencion(monkeypatch):
    """La pantalla la necesita para explicar por qué faltan los análisis viejos
    —un borrado silencioso se lee como un fallo— y para acotar el selector de
    fechas. Va en la respuesta para que salga de la configuración real."""
    monkeypatch.setattr(settings, "history_max_entries", 250)
    monkeypatch.setattr(settings, "history_max_days", 7)

    retencion = client.get("/history").json()["retention"]
    assert retencion == {"max_entries": 250, "max_days": 7}
