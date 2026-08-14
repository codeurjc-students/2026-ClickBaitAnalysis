"""Mide el coste real de las 'ineficiencias' senaladas en history.py.

Evidencia de las tablas de la seccion #102 del README. Una revision externa
senalo cinco puntos de rendimiento; medirlos descarto tres y destapo uno que no
estaba en la lista.

No toca el repo: crea su propia base de datos en un temporal de WSL (ext4),
no en /mnt/c, para que los numeros sean representativos del entorno real.

RESULTADOS (2026-08-13, WSL2 ext4 sobre VHD, Python 3.12.3 / SQLite 3.45.1)

    Path.mkdir(parents=True, exist_ok=True) [ya existe]        7.2 us
    sqlite3.connect + close (sin esquema)                     35.1 us
    sqlite3.connect + CREATE TABLE IF NOT EXISTS + close      97.4 us
    CREATE TABLE IF NOT EXISTS solo (conexion ya abierta)      9.9 us
    _conectar() + INSERT + commit [journal=delete]        193 791.9 us

    => el esquema es el 0.005 % de una escritura completa
    => el mkdir   es el 0.004 %

    descriptores tras 2000 escrituras sin close()          delta +20
    timeout por defecto de sqlite3.connect, medido          5.01 s

CONCLUSIONES

1. Ejecutar el esquema y el mkdir en cada conexion es ruido: se quedan, porque
   hacen que el sistema funcione recien clonado el repo.
2. El salto 35 -> 97 us NO es el coste del DDL: sqlite3.connect() es perezoso y
   no abre el fichero hasta la primera sentencia, que aqui es el CREATE TABLE.
   El coste marginal honesto es el aislado, 9.9 us.
3. El timeout que se proponia anadir ya existia (5 s por defecto).
4. Los 20 descriptores obligaron a un segundo banco:
   ver bench_historial_descriptores_y_wal.py
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ESQUEMA = """
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

INSERT = """
INSERT INTO history (created_at, kind, origin, headline, tool, verdict, status, payload)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

RAIZ = Path(tempfile.mkdtemp())
DB = RAIZ / "var" / "history.db"
DB.parent.mkdir(parents=True, exist_ok=True)

# Un payload realista: la respuesta de /analyze con cinco senales ronda 2-4 KB.
PAYLOAD = json.dumps({"signals": [{"name": f"s{i}", "detail": "x" * 400} for i in range(5)]})
FILA = ("2026-08-13T12:00:00+00:00", "analysis", "api", "Titular", None, "clickbait", "ok", PAYLOAD)


def bench(nombre, fn, n=2000):
    fn()  # calentar
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    us = (time.perf_counter() - t0) / n * 1e6
    print(f"  {nombre:<52} {us:9.1f} us/op   (n={n})", flush=True)
    return us


def descriptores():
    return len(os.listdir(f"/proc/{os.getpid()}/fd"))


con = sqlite3.connect(DB)
con.execute(ESQUEMA)
con.close()

print(f"\nBase de datos: {DB}", flush=True)
print(f"Python: {sys.version.split()[0]}  |  SQLite: {sqlite3.sqlite_version}", flush=True)

print("\n--- Mejora 3: mkdir en cada conexion ---", flush=True)
t_mkdir = bench("Path.mkdir(parents=True, exist_ok=True) [ya existe]",
                lambda: DB.parent.mkdir(parents=True, exist_ok=True), n=20000)

print("\n--- Mejora 1: DDL en cada conexion ---", flush=True)
bench("sqlite3.connect + close (sin esquema)", lambda: sqlite3.connect(DB).close())


def connect_con_esquema():
    c = sqlite3.connect(DB)
    c.execute(ESQUEMA)
    c.close()


bench("sqlite3.connect + CREATE TABLE IF NOT EXISTS + close", connect_con_esquema)

abierta = sqlite3.connect(DB)
t_ddl = bench("CREATE TABLE IF NOT EXISTS solo (conexion ya abierta)",
              lambda: abierta.execute(ESQUEMA), n=20000)
abierta.close()

print("\n--- Referencia: el _conectar() + INSERT completo tal cual esta hoy ---", flush=True)


def guardar_actual():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute(ESQUEMA)
    with c:
        c.execute(INSERT, FILA)


modo = sqlite3.connect(DB).execute("PRAGMA journal_mode").fetchone()[0]
t_total = bench(f"_conectar() + INSERT + commit  [journal_mode={modo}]", guardar_actual, n=200)

print(f"\n  => el esquema es el {t_ddl / t_total * 100:.3f}% de una escritura completa", flush=True)
print(f"  => el mkdir   es el {t_mkdir / t_total * 100:.3f}% de una escritura completa", flush=True)

print("\n--- Mejora 4: la conexion sin close(), fuga o no ---", flush=True)
antes = descriptores()
for _ in range(2000):
    guardar_actual()
despues = descriptores()
print(f"  descriptores abiertos antes de 2000 escrituras : {antes}", flush=True)
print(f"  descriptores abiertos despues                  : {despues}", flush=True)
print(f"  DELTA                                          : {despues - antes}", flush=True)

print("\n--- Mejora 2a: journal_mode DELETE (por defecto) vs WAL ---", flush=True)
c = sqlite3.connect(DB)
c.execute("PRAGMA journal_mode=WAL")
c.close()
modo_wal = sqlite3.connect(DB).execute("PRAGMA journal_mode").fetchone()[0]
print(f"  journal_mode tras el PRAGMA                    : {modo_wal}", flush=True)
bench(f"_conectar() + INSERT + commit  [journal_mode={modo_wal}]", guardar_actual, n=200)

c = sqlite3.connect(DB)
print(f"  journal_mode en una conexion NUEVA             : "
      f"{c.execute('PRAGMA journal_mode').fetchone()[0]}  <- persistente, no hay que repetirlo",
      flush=True)
c.close()
print(f"  ficheros en var/                               : "
      f"{sorted(p.name for p in DB.parent.iterdir())}", flush=True)

print("\n--- Mejora 2b: el timeout por defecto, medido ---", flush=True)
bloqueador = sqlite3.connect(DB)
bloqueador.execute("BEGIN EXCLUSIVE")

otro = sqlite3.connect(DB)  # sin pasar timeout: el que venga por defecto
t0 = time.perf_counter()
try:
    otro.execute(INSERT, FILA)
    print("  (no llego a bloquearse)", flush=True)
except sqlite3.OperationalError as exc:
    print(f"  espero {time.perf_counter() - t0:.2f} s antes de rendirse -> {exc}", flush=True)
otro.close()
bloqueador.rollback()
bloqueador.close()
