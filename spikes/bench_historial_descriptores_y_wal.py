"""Dos preguntas que dejo abiertas el primer banco de pruebas.

A) Los 20 descriptores de delta, .crecen sin limite (fuga) o son un atasco
   acotado esperando al recolector de ciclos?
B) WAL bajo de 193 ms a 119 ms. .Donde esta el resto? .Lo quita synchronous?

Evidencia de las tablas de la seccion #102 del README.

RESULTADOS (2026-08-13, WSL2 ext4 sobre VHD, Python 3.12.3 / SQLite 3.45.1)

  A) descriptores abiertos, patron actual (sin close)
       n=   500   delta= 75   tras gc.collect()= 0
       n=  2000   delta= 96   tras gc.collect()= 0
       n=  8000   delta= 99   tras gc.collect()= 0
       n= 20000   delta=163   tras gc.collect()= 0
       n= 20000 CON close()   delta=  0

  B) coste de una escritura completa
       journal=DELETE, synchronous=FULL  (por defecto)     164.17 ms
       journal=WAL,    synchronous=FULL                    226.00 ms
       journal=WAL,    synchronous=NORMAL                  250.66 ms
       journal=WAL,    synchronous=OFF                       0.47 ms

CONCLUSIONES

A) No es una fuga lineal (20 000 escrituras no dejan 20 000 descriptores), pero
   el atasco CRECE y gc.collect() lo devuelve siempre a cero: son conexiones
   esperando al recolector de CICLOS, no al contador de referencias. El codigo
   era correcto por accidente, apoyado en un detalle de CPython que PyPy no
   comparte. Con close() explicito el delta es 0 exacto.

B) WAL sale MAS LENTO, al reves de lo que dice el manual. Al cerrar la ULTIMA
   conexion a una base en modo WAL, SQLite ejecuta un checkpoint completo, y con
   'una conexion por operacion' eso pasa en cada escritura. WAL rinde cuando las
   conexiones se mantienen abiertas: son dos decisiones acopladas, y quedarse
   con media de cada una es peor que con cualquiera entera.

   Los 0.47 ms de synchronous=OFF prueban que los ~164 ms son TODO fsync. No se
   toca: es el unico cambio evaluado que sacrifica una garantia real. Ojo con
   extrapolar la cifra: medida sobre el disco virtual de WSL2, donde el fsync
   atraviesa hasta el anfitrion Windows. En Linux nativo son decimas de ms.
   Volver a medirlo al contenerizar (H4).
"""

import gc
import json
import os
import sqlite3
import sys
import tempfile
import time
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
PAYLOAD = json.dumps({"signals": [{"name": f"s{i}", "detail": "x" * 400} for i in range(5)]})
FILA = ("2026-08-13T12:00:00+00:00", "analysis", "api", "Titular", None, "clickbait", "ok", PAYLOAD)


def fds():
    return len(os.listdir(f"/proc/{os.getpid()}/fd"))


def nueva_db(pragmas=()):
    ruta = Path(tempfile.mkdtemp()) / "history.db"
    c = sqlite3.connect(ruta)
    for p in pragmas:
        c.execute(p)
    c.execute(ESQUEMA)
    c.close()
    return ruta


print(f"Python: {sys.version.split()[0]}  |  SQLite: {sqlite3.sqlite_version}\n", flush=True)

# ---------------------------------------------------------------- A
print("=== A) .Fuga lineal o atasco acotado? ===", flush=True)
print("   (synchronous=OFF solo para que corra rapido; no afecta al ciclo de vida)\n", flush=True)


def escribir_sin_close(ruta):
    """El patron ACTUAL: `with conexion:` sin close()."""
    c = sqlite3.connect(ruta)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA synchronous=OFF")
    c.execute(ESQUEMA)
    with c:
        c.execute(INSERT, FILA)


for n in (500, 2000, 8000, 20000):
    ruta = nueva_db(("PRAGMA journal_mode=WAL", "PRAGMA synchronous=OFF"))
    gc.collect()
    antes = fds()
    for _ in range(n):
        escribir_sin_close(ruta)
    pico = fds()
    gc.collect()
    tras_gc = fds()
    print(f"  n={n:>6}   antes={antes:>3}   despues={pico:>3}   "
          f"delta={pico - antes:>3}   tras gc.collect()={tras_gc:>3}", flush=True)

print("\n  -> si el delta NO crece con n, es un atasco acotado, no una fuga", flush=True)
print("  -> si gc.collect() lo devuelve al inicio, estaban esperando al recolector", flush=True)

# Y el patron PROPUESTO, para contrastar
print("\n  Con close() explicito:", flush=True)


def escribir_con_close(ruta):
    c = sqlite3.connect(ruta)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA synchronous=OFF")
    c.execute(ESQUEMA)
    try:
        with c:
            c.execute(INSERT, FILA)
    finally:
        c.close()


ruta = nueva_db(("PRAGMA journal_mode=WAL", "PRAGMA synchronous=OFF"))
gc.collect()
antes = fds()
for _ in range(20000):
    escribir_con_close(ruta)
print(f"  n= 20000   antes={antes:>3}   despues={fds():>3}   delta={fds() - antes:>3}", flush=True)

# ---------------------------------------------------------------- B
print("\n=== B) .De donde salen los 119 ms que quedan? ===\n", flush=True)


def bench_escritura(etiqueta, pragmas, n=200):
    ruta = nueva_db(pragmas)

    def escribir():
        c = sqlite3.connect(ruta)
        for p in pragmas:
            c.execute(p)
        c.execute(ESQUEMA)
        try:
            with c:
                c.execute(INSERT, FILA)
        finally:
            c.close()

    escribir()
    t0 = time.perf_counter()
    for _ in range(n):
        escribir()
    ms = (time.perf_counter() - t0) / n * 1e3
    print(f"  {etiqueta:<48} {ms:9.2f} ms/op", flush=True)
    return ms


base = bench_escritura("journal=DELETE, synchronous=FULL  (por defecto)", ())
wal = bench_escritura("journal=WAL,    synchronous=FULL", ("PRAGMA journal_mode=WAL",))
wal_normal = bench_escritura(
    "journal=WAL,    synchronous=NORMAL  <-- propuesta",
    ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL"),
)
wal_off = bench_escritura(
    "journal=WAL,    synchronous=OFF     (sin durabilidad)",
    ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=OFF"),
)

print(f"\n  WAL+FULL   frente al defecto : {base / wal:5.1f}x mas rapido", flush=True)
print(f"  WAL+NORMAL frente al defecto : {base / wal_normal:5.1f}x mas rapido", flush=True)
print(f"  WAL+OFF    frente al defecto : {base / wal_off:5.1f}x mas rapido", flush=True)
