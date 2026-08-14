"""Formulaciones de la poda por cantidad: .convergen, y cuanto cuestan?

El banco anterior midio la variante (c) -borrar solo la mas vieja- empezando
justo en el limite, asi que el '-> quedan 1000 filas' salio por construccion y
no porque la poda funcione. (c) borra incondicionalmente: MANTIENE el tamano de
partida, no converge al limite.

Aqui se comprueba lo que de verdad importa de una poda: que desde CUALQUIER
tamano inicial acabe en el limite. Y ademas cuanto cuesta hacerlo.

RESULTADOS (2026-08-14, limite fijo en 1000)

  0) AUTOINCREMENT y los huecos
       tras 1 insercion REVERTIDA y 1 confirmada, el id de la fila es 1
       -> NO quema el id al revertir: el contador se deshace con la transaccion

  1) convergencia (200 escrituras con poda)
                                     desde 500    desde 3000
       (a) MIN sobre subconsulta       -> 700       -> 1000    OK
       (c) mas vieja, SIN guarda       -> 500       -> 3000    NO CONVERGE
       (d) corte por MAX(id) - N       -> 700       -> 1000    OK

  2) coste en regimen estacionario (solo la poda, sin el INSERT)
       (a) MIN sobre subconsulta       801.08 us
       (c) mas vieja, SIN guarda        14.39 us
       (d) corte por MAX(id) - N        17.71 us

CONCLUSIONES

Gana (d): converge desde ambos lados y es 45x mas barata que (a).

(c) queda descartada aunque sea la mas rapida: NO converge. Borra
incondicionalmente, asi que MANTIENE el tamano de partida — con 500 filas y techo
de 1000 seguia borrando una por escritura, que es perdida de datos silenciosa.
Barata e incorrecta, la peor combinacion.

Las dos mitades del criterio significan cosas distintas:
  - Desde ABAJO es CORRECCION: borrar por debajo del limite destruye datos que la
    politica dice conservar.
  - Desde ARRIBA es la RUTA DE ACTUALIZACION, y no es hipotetica: el historial
    lleva creciendo sin techo desde #102, asi que al desplegar la retencion lo
    primero que se encuentra es una tabla por encima del limite. Que (d) reduzca
    de golpe —de 3000 a 1000 en UNA sentencia— es lo que evita una migracion.

Sobre el punto 0: la prueba de huecos resulto VACUA. Se crearon 100 inserciones
revertidas esperando huecos y no hay huecos que crear. Que (d) salga clavada en
1000 es correcto, pero no por resistir huecos: por no haberlos. Los ids son
contiguos en este diseno —la poda borra por la cola y el rollback no quema ids—,
y eso es lo que convierte a (d) de aproximada en EXACTA.
"""

import json
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
    kind TEXT NOT NULL, origin TEXT NOT NULL, headline TEXT, tool TEXT,
    verdict TEXT, status TEXT NOT NULL, payload TEXT NOT NULL);
"""
INSERT = """
INSERT INTO history (created_at, kind, origin, headline, tool, verdict, status, payload)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

PODA_A = ("(a) MIN sobre subconsulta",
          "DELETE FROM history WHERE id < "
          "(SELECT MIN(id) FROM (SELECT id FROM history ORDER BY id DESC LIMIT ?))")
PODA_C = ("(c) mas vieja, SIN guarda",
          "DELETE FROM history WHERE id = (SELECT MIN(id) FROM history)")
PODA_D = ("(d) corte por MAX(id) - N",
          "DELETE FROM history WHERE id <= (SELECT MAX(id) FROM history) - ?")

PAYLOAD = json.dumps({"signals": [{"n": f"s{i}", "d": "x" * 400} for i in range(5)]})
AHORA = datetime.now(timezone.utc)
LIMITE = 1000


def fila(dias=0):
    return ((AHORA - timedelta(days=dias)).isoformat(), "analysis", "api",
            "Un titular", None, "clickbait", "ok", PAYLOAD)


def db(filas=0):
    ruta = Path(tempfile.mkdtemp()) / "history.db"
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA synchronous=OFF")
    con.execute(ESQUEMA)
    if filas:
        with con:
            con.executemany(INSERT, [fila() for _ in range(filas)])
    return con


def contar(con):
    return con.execute("SELECT COUNT(*) FROM history").fetchone()[0]


print(f"Python {sys.version.split()[0]} | SQLite {sqlite3.sqlite_version}")
print(f"Limite = {LIMITE}\n")

# ------------------------------------------------------------------ 0
print("=== 0) .AUTOINCREMENT quema el id al revertir la transaccion? ===")
print("    Es de donde vienen los huecos, y de lo que depende que (d) sea")
print("    conservadora en vez de incorrecta.\n")

con = db()
con.execute("BEGIN")
con.execute(INSERT, fila())
con.execute("ROLLBACK")
con.execute("BEGIN")
con.execute(INSERT, fila())
con.commit()
primero = con.execute("SELECT MIN(id) FROM history").fetchone()[0]
print(f"  tras 1 insercion REVERTIDA y 1 confirmada, el id de la fila es: {primero}")
print(f"  -> {'SI quema el id (hay huecos)' if primero > 1 else 'NO quema el id (sin huecos)'}\n")
con.close()

# ------------------------------------------------------------------ 1
print("=== 1) .Converge al limite desde cualquier tamano de partida? ===")
print("    200 escrituras con poda. Desde 500 deberia CRECER hacia 700 (nada")
print("    que podar). Desde 3000 deberia BAJAR a 1000.\n")

for etiqueta, sql in (PODA_A, PODA_C, PODA_D):
    parametros = () if sql == PODA_C[1] else (LIMITE,)
    resultados = []
    for inicial in (500, 3000):
        con = db(inicial)
        for _ in range(200):
            with con:
                con.execute(INSERT, fila())
                con.execute(sql, parametros)
        resultados.append((inicial, contar(con)))
        con.close()
    detalle = "   ".join(f"desde {i} -> {f}" for i, f in resultados)
    ok = resultados[0][1] == 700 and resultados[1][1] == LIMITE
    print(f"  {etiqueta:<32} {detalle:<34} {'OK' if ok else 'NO CONVERGE'}")

# ------------------------------------------------------------------ 2
print("\n=== 2) Coste en regimen estacionario (solo la poda, sin el INSERT) ===\n")

for etiqueta, sql in (PODA_A, PODA_C, PODA_D):
    parametros = () if sql == PODA_C[1] else (LIMITE,)
    con = db(LIMITE)
    tiempos = []
    for _ in range(1000):
        con.execute(INSERT, fila())
        t0 = time.perf_counter()
        con.execute(sql, parametros)
        tiempos.append(time.perf_counter() - t0)
    con.commit()
    media = sum(tiempos) / len(tiempos) * 1e6
    print(f"  {etiqueta:<32} {media:9.2f} us/op   -> quedan {contar(con)} filas")
    con.close()

# ------------------------------------------------------------------ 3
print("\n=== 3) Con huecos, .cuanto por DEBAJO del limite se queda (d)? ===")
print("    Un hueco hace que el corte caiga mas arriba: guarda algo menos de")
print("    1000, nunca mas. La pregunta es cuanto menos.\n")

for huecos in (0, 10, 100):
    con = db(LIMITE)
    for _ in range(huecos):  # inserciones revertidas: queman id, no dejan fila
        try:
            with con:
                con.execute(INSERT, fila())
                raise RuntimeError
        except RuntimeError:
            pass
    for _ in range(200):
        with con:
            con.execute(INSERT, fila())
            con.execute(PODA_D[1], (LIMITE,))
    print(f"  {huecos:>3} inserciones revertidas -> la tabla se estabiliza en "
          f"{contar(con)} filas  (techo {LIMITE})")
    con.close()
