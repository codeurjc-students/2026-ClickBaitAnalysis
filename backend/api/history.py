"""Almacén del historial de análisis.

**Qué se guarda: análisis, no invocaciones.** R9 habla de registrar cada
ejecución de herramienta, pero un solo ``POST /analyze`` invoca cinco: guardarlas
sueltas daría una pantalla llena de ``detect_clickbait_lexical`` en vez del
titular que el usuario analizó. La traza de invocaciones ya existe —
``log_tool_invocation`` la registra con parámetros y duración— y sirve para
depurar, que es su sitio. Aquí se guarda lo que el usuario reconoce.

Se guarda la respuesta **completa** porque el prototipo pide «acceso al
resultado». Reejecutar en vez de guardar no valdría: costaría ~20 s y las
señales remotas no son deterministas, así que el «resultado anterior» podría
salir distinto — lo contrario de un historial.

**SQLite detrás de tres funciones.** Lo que protege de un cambio de requisitos no
es elegir el almacén más flexible, sino aislarlo: cambiar de motor es reescribir
este fichero, sin tocar endpoints ni sus tests. Se elige SQLite porque tiene paginación, filtros y orden
inverso: con JSONL cada consulta leería el fichero entero.
"""

import asyncio
import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

# `HistoryKind` y `Origin` viven en `schemas.py`, no aquí, porque TODOS los enums
# del contrato están allí y el cliente Angular se genera del esquema OpenAPI: un
# enum publica el conjunto cerrado de valores, una cadena suelta no.
from backend.api.schemas import HistoryKind, Origin
from backend.config.settings import settings

log = structlog.get_logger()

# `__file__` es .../backend/api/history.py, así que dos niveles por encima está la
# raíz del repo. Se ancla ahí porque `settings.history_db` es RELATIVA, y una ruta
# relativa se resuelve contra el directorio desde el que se arrancó el proceso:
# lanzar uvicorn desde `backend/` en vez de desde la raíz crearía una SEGUNDA base
# de datos vacía. Y como `_conectar` la crea sin quejarse, el síntoma no sería un
# error sino «se ha borrado el historial».
_RAIZ = Path(__file__).resolve().parents[2]

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind       TEXT NOT NULL,
    origin     TEXT NOT NULL,
    headline   TEXT,
    tool       TEXT,
    verdict    TEXT,
    status     TEXT NOT NULL,
    payload    TEXT NOT NULL
);
"""

# Va como sentencia aparte porque `execute` ejecuta UNA sola: pegarlo al final
# de `_ESQUEMA` no lo crearía. (`executescript` sí acepta varias, pero emite un
# COMMIT implícito antes, y eso dentro de una transacción es lo contrario de lo
# que queremos.)
#
# Sin este índice, `created_at < ?` recorre y compara la tabla entera. Medido
# sobre 1000 filas: 2374 µs sin índice frente a 0,99 µs con él, y la diferencia
# CRECE con el tamaño (54 595 µs a 50 000 filas, frente a los mismos ~1 µs).
# Y no se paga al insertar: 14,29 µs sin índice contra 13,91 µs con él, o sea
# por debajo del ruido de medida.
_INDICE_FECHA = (
    "CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at)"
)


def _ruta_db() -> Path:
    """Ruta absoluta del fichero, ancle donde ancle la configuración.

    Una ruta ABSOLUTA en `settings` se respeta tal cual: es lo que se pondrá en el
    contenedor (`HISTORY_DB=/var/lib/clickbait/history.db`). Sólo las relativas se
    anclan a la raíz del repo.
    """
    ruta = Path(settings.history_db)
    return ruta if ruta.is_absolute() else _RAIZ / ruta


@contextmanager
def _conectar() -> Generator[sqlite3.Connection, None, None]:
    """Abre la base de datos, creándola y creando el esquema si hace falta.

    Una conexión por operación: sin pool ni estado compartido. A este volumen
    —una escritura por análisis— la simplicidad gana, y evita tener que
    responder si la conexión aguanta uso concurrente.

    Es un gestor de contexto propio y no un `sqlite3.connect` pelado porque el
    `with` de una conexión de sqlite3 **NO la cierra**: gestiona la TRANSACCIÓN
    (commit al salir bien, rollback si salta una excepción). Sin el `close()`
    explícito, cerrarla queda en manos del recolector de basura — medido: 20 000
    escrituras dejaban hasta 163 descriptores abiertos, que un `gc.collect()`
    devolvía a cero. No es una fuga lineal, pero el momento del cierre es
    impredecible, y en un intérprete sin conteo de referencias (PyPy) sí crecería.
    Con este `finally` el delta medido es 0 exacto.

    El orden importa: el `with` interno sale ANTES que el `finally`, así que
    primero confirma y luego cierra. Al revés se perdería la escritura, porque
    cerrar una conexión con una transacción pendiente la deshace.

    NO se activa `PRAGMA journal_mode=WAL`, aunque sea la recomendación habitual
    para aplicaciones web. Medido con este patrón de acceso sale MÁS LENTO:
    164 ms → 226 ms por escritura. Al cerrar la última conexión a una base en modo
    WAL, SQLite ejecuta un checkpoint completo, y con una conexión por operación
    eso pasa en cada escritura. WAL rinde cuando las conexiones se mantienen
    abiertas, que es justo lo que este diseño no hace: son dos decisiones
    acopladas, y quedarse con media de cada una es peor que con cualquiera entera.
    """
    ruta = _ruta_db()
    ruta.parent.mkdir(
        parents=True, exist_ok=True
    )  # No se trae el repo /var de primeras, así que lo crea si no existe.

    conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row  # Usar Row para poder acceder a las columnas por nombre en lugar de por índice. (fila["columna"] en lugar de fila[0])
    conexion.execute(_ESQUEMA)
    conexion.execute(_INDICE_FECHA)
    try:
        with conexion:  # transacción: commit al salir bien, rollback si hay excepción
            yield conexion
    finally:
        conexion.close()  # el `with` de arriba NO cierra, sólo transacciona


# Las columnas `tool`, `verdict` y `status` existen ya aunque el filtrado sea
# otro issue (#103): añadir una columna después obliga a migrar, y declararlas
# ahora no cuesta nada.
_INSERT = """
INSERT INTO history (created_at, kind, origin, headline, tool, verdict, status, payload)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

# ? son placeholders que se sustituyen por los valores de la tupla en el segundo argumento de execute. Esto evita inyecciones SQL y problemas de comillas.


def _marca(momento: datetime) -> str:
    """Convierte una fecha en el texto que se guarda: ISO 8601 en UTC.

    **Pasa por aquí TODO lo que toca `created_at`** —lo que se escribe, el corte
    de la poda y los filtros—, y esa es la razón de que exista en vez de llamar a
    `isoformat()` en cada sitio.

    El motivo: `created_at` se compara **entre cadenas**, y eso sólo reproduce el
    orden cronológico si todas están escritas igual. Comprobado que hoy lo están,
    y que las comparaciones aciertan incluso mezclando marcas con microsegundos y
    sin ellos —el carácter que sigue a los segundos es `.` (46) si los hay y `+`
    (43) si no, y 46 > 43, que es justo el orden correcto—.

    Pero era correcto **por un invariante que nada imponía**: que tres sitios
    distintos se acordaran de usar `isoformat()` en UTC. La demostración de qué
    pasaría si uno se despistara: un sufijo `Z` es el carácter 90, ordena después
    de CUALQUIER desfase, y mezclarlo con `+00:00` sí rompe las comparaciones —en
    silencio, descartando o colando filas sin ningún error. Centralizarlo aquí no
    arregla un fallo: arregla que la corrección dependa de la memoria de quien
    escriba el siguiente `INSERT`.

    Una fecha sin huso se toma como UTC y no como hora local, para que el
    resultado no dependa de la máquina donde corra el servidor.
    """
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC).isoformat()


def _ahora() -> str:
    """El instante actual, en el formato en que se guarda."""
    return _marca(datetime.now(UTC))


# Poda por cantidad. Parece la fórmula ingenua —«resta N al mayor id»— y hay que
# explicar por qué aquí es EXACTA, porque a simple vista no lo parece.
#
# Restar del máximo sólo da «la N-ésima más nueva» si los ids son CONTIGUOS. Lo
# son, y está comprobado: la poda borra siempre por la cola, así que deja un
# bloque sin huecos; y `AUTOINCREMENT` NO quema el id al revertir una transacción
# —el contador se deshace con ella—, así que una inserción fallida tampoco los
# crea. Lo que `AUTOINCREMENT` garantiza es otra cosa: que un id no se REUTILICE
# tras borrar, para que el 40 podado no reaparezca señalando otro análisis.
#
# Si algún día algo borrara filas del MEDIO (p. ej. «fijar un análisis para que
# no se pierda»), aparecerían huecos, el corte caería más arriba y se conservarían
# algo MENOS de N. Nunca más: el techo se respeta siempre, sólo el suelo se vuelve
# aproximado.
#
# Se eligió frente a la subconsulta con MIN (801 µs) porque cuesta 17,7 µs y es
# constante con el tamaño de la tabla: `MAX(id)` es el extremo derecho del índice
# de la clave primaria, y `id <= corte` arranca por el izquierdo y para enseguida.
# Se descartó «borrar sólo la más vieja» (14,4 µs) porque NO converge: mantiene el
# tamaño de partida en vez de llevarlo al límite, así que con 500 filas y techo de
# 1000 seguía borrando una por escritura. Barata e incorrecta.
_PODA_CANTIDAD = "DELETE FROM history WHERE id <= (SELECT MAX(id) FROM history) - ?"

# Poda por antigüedad. La comparación de cadenas basta porque las marcas se
# guardan en ISO 8601, donde el orden alfabético coincide con el cronológico.
_PODA_ANTIGUEDAD = "DELETE FROM history WHERE created_at < ?"


def _podar(conexion: sqlite3.Connection) -> None:
    """Recorta el historial a los límites configurados. `0` desactiva cada uno.

    Se ejecuta AL ESCRIBIR, dentro de la transacción del `INSERT`. Es lo que hace
    que salga prácticamente gratis: una escritura ya paga un `fsync`, y estas dos
    sentencias viajan en ese mismo commit sin añadir otro (medido: ninguna
    variante se acercó al doble de la referencia).

    Las otras dos opciones se descartaron. **Programada** exige un proceso vivo y
    un planificador para algo que aquí no lo necesita. **Al leer** es lo peor de
    ambas: convierte una consulta en una operación destructiva.

    Que la poda por cantidad reduzca —y no sólo mantenga— es lo que evita tener
    que escribir una migración: al desplegar esto sobre una base que ya venía
    creciendo sin techo, la primera escritura la deja en su sitio de una sola
    sentencia. (Si nadie escribe, nadie poda: la tabla se queda como está, que es
    inofensivo porque tampoco crece, y se corrige con el primer análisis.)
    """
    if settings.history_max_entries > 0:
        conexion.execute(_PODA_CANTIDAD, (settings.history_max_entries,))

    if settings.history_max_days > 0:
        corte = datetime.now(UTC) - timedelta(days=settings.history_max_days)
        conexion.execute(_PODA_ANTIGUEDAD, (_marca(corte),))


def _guardar(
    kind: HistoryKind,
    origin: Origin,
    status: str,
    payload: dict[str, Any],
    headline: str | None,
    tool: str | None,
    verdict: str | None,
) -> int:
    with _conectar() as conexion:
        cursor = conexion.execute(
            _INSERT,
            (
                _ahora(),
                kind.value,
                origin.value,
                headline,
                tool,
                verdict,
                status,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        identificador = cursor.lastrowid  # Devuelve el id de la fila insertada, que es útil para referenciarla después.

        # Va DENTRO de la misma transacción, a propósito: es lo que hace que se
        # cuele en el `fsync` que el INSERT ya estaba pagando.
        #
        # El precio de esa decisión: si la poda falla, se deshace también el
        # INSERT, y como `record` se traga los errores el síntoma sería «el
        # historial dejó de guardar» sin ruido. Separarlas en dos transacciones lo
        # evitaría, pero perdería el ahorro que justifica podar al escribir.
        _podar(conexion)

        return identificador


async def record(
    kind: HistoryKind,
    origin: Origin,
    status: str,
    payload: dict[str, Any],
    headline: str | None = None,
    tool: str | None = None,
    verdict: str | None = None,
) -> int | None:
    """Registra una entrada. Devuelve su id, o None si no se pudo guardar.

    **Un fallo aquí no se propaga**, y conviene distinguirlo de tragarse un
    error: lo que falla es un *efecto colateral*, no la respuesta. El análisis ya
    se hizo y es correcto; perderlo porque el disco esté lleno sería peor que no
    guardarlo. El motivo queda en el log.

    (No es el caso de ``log_tool_invocation``, que devolvía una cadena en lugar
    del resultado del que se le preguntaba: allí lo tragado ERA la respuesta.)
    """
    try:
        # Guardar en un hilo aparte para no bloquear el bucle de eventos. SQLite es rápido, pero no instantáneo: si se bloquea el bucle de eventos, la API deja de responder y el usuario ve un timeout.
        return await asyncio.to_thread(
            _guardar, kind, origin, status, payload, headline, tool, verdict
        )
    except Exception as exc:
        log.error("historial.escritura_fallida", motivo=f"{type(exc).__name__}: {exc}")
        return None


def _condiciones(
    kind: HistoryKind | None,
    tool: str | None,
    verdict: str | None,
    status: str | None,
    since: datetime | None,
    until: datetime | None,
) -> tuple[str, list[Any]]:
    """Construye el `WHERE` con los filtros que vengan, y sus valores aparte.

    Esto COMPONE una cadena SQL, que es el patrón que a primera vista parece una
    inyección. La regla que hay que cumplir no es «el texto tiene que ser un
    literal», sino algo más preciso: **ningún dato que venga de fuera puede
    llegar al texto de la consulta**. Aquí lo que se acumula en `condiciones` son
    fragmentos escritos en este fichero; los valores del usuario viajan aparte,
    por `?`, en la lista de parámetros.

    Los fragmentos van ENTEROS en la tupla (`"kind = ?"`) y no compuestos con un
    f-string a partir del nombre de columna. Compuestos también serían seguros
    —el nombre saldría igualmente de aquí— pero lo serían por DÓNDE viene esa
    variable, no por cómo está escrita la línea: un invariante que vive a tres
    líneas de distancia y que nada impone. El día que alguien añada un filtro
    genérico por campo y pase el nombre desde la petición, esa misma línea se
    convierte en una inyección sin dar ninguna señal. Un literal no puede
    degradarse así.

    Los filtros se combinan con AND: son restricciones acumulativas, que es lo
    que espera quien va marcando casillas en una pantalla.
    """
    condiciones: list[str] = []
    valores: list[Any] = []

    # `tool` sólo tiene sentido sobre las ejecuciones sueltas: un análisis invocó
    # CINCO herramientas, así que no hay una por la que filtrarlo. En la pantalla
    # eso se resuelve mostrando el desplegable de herramientas únicamente dentro
    # de la pestaña «Herramientas», de modo que la restricción no se explica: se
    # ve. Aquí simplemente no casará con ninguna entrada de análisis, porque su
    # columna `tool` es nula.
    for condicion, valor in (
        ("kind = ?", kind.value if kind else None),
        ("tool = ?", tool),
        ("verdict = ?", verdict),
        ("status = ?", status),
    ):
        # `is not None` y no `if valor`: una cadena vacía o un 0 son valores
        # legítimos, y con la comprobación por verdad se tratarían como «no vino».
        if valor is not None:
            condiciones.append(condicion)
            valores.append(valor)

    if since is not None:
        condiciones.append("created_at >= ?")
        valores.append(_marca(since))
    if until is not None:
        condiciones.append("created_at <= ?")
        valores.append(_marca(until))

    where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""
    return where, valores


def _leer(
    limit: int,
    offset: int,
    kind: HistoryKind | None = None,
    tool: str | None = None,
    verdict: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[
    list[dict[str, Any]], int
]:  # Devuelve una página del historial y el total de entradas. El total lo necesita la interfaz para paginar («1-20 de 137»); sin él sólo puede saber si hay más página probando a pedirla.

    # Tuple: Devuelve una tupla con dos elementos: una lista de diccionarios que representan las entradas del historial y un entero que indica el total de entradas en la base de datos.
    # Dict[str, Any]: Cada diccionario tiene claves de tipo str y valores de cualquier tipo (Any), lo que permite almacenar información diversa sobre cada entrada del historial.

    where, valores = _condiciones(kind, tool, verdict, status, since, until)

    with _conectar() as conexion:
        # El COUNT lleva el MISMO `WHERE` que la consulta: el total tiene que ser
        # el de las entradas que casan con el filtro, no el de la tabla entera, o
        # la interfaz pintaría «1-3 de 500» sobre una lista de tres.
        total = conexion.execute(
            f"SELECT COUNT(*) FROM history{where}", valores
        ).fetchone()[0]
        # fetchone() devuelve una tupla con un solo elemento, que es el resultado de la consulta COUNT(*). Se accede a ese elemento con [0] para obtener el número total de entradas en la tabla history.
        # Orden por id descendente: más estable que timestamp.
        #
        # Las columnas se nombran en vez de usar `SELECT *`, aunque suponga
        # repetirlas por tercera vez en este fichero (ya están en `_ESQUEMA` y en
        # `_INSERT`). Eso NO es acoplamiento: el acoplamiento es una propiedad de
        # las fronteras entre módulos, y éste es justo el módulo cuyo trabajo es
        # saberse el esquema. `SELECT *` no elimina ese conocimiento, lo DELEGA a
        # quien consuma el resultado — que está al otro lado de la frontera.
        #
        # Consecuencia concreta: como `app.py` hace `HistoryEntry(**fila)`, con
        # `SELECT *` la forma de la tabla decide la del contrato. Medido: añadir
        # una columna se ignora en silencio, y RENOMBRAR una deja su campo a None
        # también en silencio —titulares vacíos en la interfaz, sin un solo error
        # en ningún log—. Nombrarlas convierte la salida de este módulo en una
        # declaración deliberada, y mueve el fallo aquí dentro, que es su sitio.
        filas = conexion.execute(
            "SELECT id, created_at, kind, origin, headline, tool, verdict, status, payload "
            f"FROM history{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*valores, limit, offset),
        ).fetchall()

        # LIMIT ? OFFSET ? es la paginación: "sáltate offset filas y dame las limit siguientes". Página 1: LIMIT 20 OFFSET 0; página 2 : LIMIT 20 OFFSET 20.

    return [_desempaquetar(fila) for fila in filas], total


def _desempaquetar(fila: sqlite3.Row) -> dict[str, Any]:
    """Convierte una fila en un diccionario corriente, con el payload ya parseado.

    Las dos conversiones existen por lo mismo: que nada de SQLite salga de este
    módulo. Devolver un `sqlite3.Row` obligaría a quien llame a manejar un tipo de
    la biblioteca de SQLite; devolver el payload como cadena le obligaría a saber
    que aquí dentro se guarda serializado —y con Postgres y una columna `jsonb` el
    driver ya devolvería el objeto construido, así que ese `json.loads` de fuera
    reventaría con un TypeError. El aislamiento incluye el formato, no sólo el
    motor: entra un diccionario, sale un diccionario.

    Si el JSON estuviera corrupto **falla, y dice qué fila**. Ninguna ruta del
    código puede producirlo —`_guardar` es el único sitio que escribe `payload` y
    siempre con `json.dumps`, y la columna es NOT NULL— así que esto sólo salta si
    alguien ha editado la base a mano. Aun así se identifica la entrada, porque un
    `JSONDecodeError` pelado no dice cuál de las mil está rota y obligaría a
    buscarla a ojo.

    Se descartó lo contrario —capturar y devolver `{}`— aunque evitaría que una
    fila mala dejara ilegible el historial entero: sustituye datos corruptos por
    datos falsos **en silencio**, y un sistema cuya tesis es declarar sus límites
    en vez de esconderlos no debería inventarse un payload vacío y seguir.
    """
    entrada = dict(fila)
    try:
        entrada["payload"] = json.loads(entrada["payload"])
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"El payload de la entrada {entrada['id']} no es JSON válido."
        ) from exc
    return entrada


async def query(
    limit: int,
    offset: int,
    kind: HistoryKind | None = None,
    tool: str | None = None,
    verdict: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Devuelve una página del historial y el total de entradas que casan.

    El total lo necesita la interfaz para paginar («1-20 de 137»); sin él sólo
    puede saber si hay más página probando a pedirla. Con filtros aplicados es
    el total de lo filtrado, no el de la tabla.

    `verdict` y `status` responden preguntas distintas y por eso son dos y no
    uno: el veredicto es **qué concluyó el análisis** (`enganoso`, `factual`…) y
    es el que le interesa a quien mira sus análisis; el estado es **si funcionó
    la maquinaria**, y es operativo. Meterlos en un solo parámetro «estado» era
    lo que hacía que el criterio no encajara.
    """
    return await asyncio.to_thread(
        _leer, limit, offset, kind, tool, verdict, status, since, until
    )
