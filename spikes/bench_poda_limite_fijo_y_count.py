"""Rehace la parte C del banco anterior, que tenia un fallo de diseno.

El primero paso `LIMIT = filas + 10`, es decir hizo crecer el LIMITE junto con la
tabla, asi que no midio lo que decia medir. En el sistema real el limite es FIJO
(1000) sea cual sea el tamano de la tabla.

Tres preguntas:

A) Con limite fijo, .la poda por cantidad es constante o escala con la tabla?
B) .Hay una forma mas barata de escribirla? Se comparan tres.
C) SELECT COUNT(*) lo ejecuta GET /history en CADA lectura y en SQLite no esta
   cacheado. .Cuanto cuesta segun crece la tabla? Esto afecta a lo ya mergeado.

RESULTADOS (2026-08-14, limite fijo en 1000)

  C) regimen estacionario: cada escritura borra UNA fila
       (a) MIN sobre subconsulta        683.13 us   -> quedan 1000 filas
       (b) OFFSET sobre el indice       617.86 us   -> quedan 1000 filas
       (c) borrar solo la mas vieja      16.68 us   -> quedan 1000 filas

  D) SELECT COUNT(*), que GET /history hace en CADA lectura
       sobre  1 000 filas       886 us
       sobre 10 000 filas    10 215 us
       sobre 50 000 filas    50 465 us

CONCLUSIONES

D es el hallazgo, y toca codigo YA MERGEADO: el conteo es LINEAL, ~1 us por fila,
porque SQLite no lo cachea sino que recorre. Con 50 000 entradas serian 50 ms por
peticion solo para contar. Eso convierte la retencion en algo mas que higiene de
disco: es lo que mantiene barata una lectura que ya estaba escrita.

Sobre C: el '-> quedan 1000 filas' de la variante (c) NO prueba lo que parece.
(c) borra incondicionalmente, y este banco arranco justo en 1000, asi que el
resultado salio bonito por construccion. Se destapo en
bench_poda_convergencia.py, que es el que decide.

Y la parte A/B de este banco (no incluida arriba) resulto POCO FIABLE: con limite
fijo la poda por cantidad sale plana (~1 ms) a los tres tamanos, pero TAMBIEN
sale plana al hacer crecer el limite hasta 50 010, y eso contradice al banco
anterior, que en ese mismo caso daba 62 ms. No se explica el suelo de ~1 ms y no
se construyo ninguna recomendacion sobre esos numeros: la pregunta que importaba
—el coste en regimen estacionario— la responde la medida directa de C.
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

# (a) la que propuse: subconsulta con MIN sobre las N mas nuevas
PODA_A = """
DELETE FROM history
WHERE id < (SELECT MIN(id) FROM (SELECT id FROM history ORDER BY id DESC LIMIT ?))
"""
# (b) saltar N por el indice y quedarse con ese id
PODA_B = """
DELETE FROM history
WHERE id <= (SELECT id FROM history ORDER BY id DESC LIMIT 1 OFFSET ?)
"""
# (c) borrar SOLO la mas vieja. Vale porque podamos en CADA escritura, asi que
#     como mucho sobra una fila. MIN(id) sobre la clave primaria es inmediato.
PODA_C = "DELETE FROM history WHERE id = (SELECT MIN(id) FROM history)"

PAYLOAD = json.dumps({"signals": [{"n": f"s{i}", "d": "x" * 400} for i in range(5)]})
AHORA = datetime.now(timezone.utc)
LIMITE = 1000


def fila(dias=0):
    return ((AHORA - timedelta(days=dias)).isoformat(), "analysis", "api",
            "Un titular", None, "clickbait", "ok", PAYLOAD)


def db(filas):
    ruta = Path(tempfile.mkdtemp()) / "history.db"
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA synchronous=OFF")
    con.execute(ESQUEMA)
    if filas:
        with con:
            con.executemany(INSERT, [fila(dias=(i * 60) // filas) for i in range(filas)])
    return con


def bench(etiqueta, fn, n=2000):
    fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    us = (time.perf_counter() - t0) / n * 1e6
    print(f"  {etiqueta:<50} {us:11.2f} us/op", flush=True)
    return us


print(f"Python {sys.version.split()[0]} | SQLite {sqlite3.sqlite_version}", flush=True)
print(f"Limite FIJO en {LIMITE} filas, como en el sistema real.\n", flush=True)

print("=== A/B) Poda por cantidad: .constante con el limite fijo? ===")
print("    (la poda no encuentra nada que borrar: aisla el coste de BUSCAR)\n")

for filas in (1_000, 10_000, 50_000):
    print(f"  --- tabla de {filas} filas ---", flush=True)
    con = db(filas)
    # Limite por encima del total para que no borre nada y no mute la tabla.
    tope = filas + 10
    bench(f"(a) MIN sobre subconsulta   LIMIT {LIMITE}",
          lambda: con.execute(PODA_A, (LIMITE,)))
    bench(f"(a) MIN sobre subconsulta   LIMIT {tope} (no borra)",
          lambda: con.execute(PODA_A, (tope,)))
    bench(f"(b) OFFSET sobre el indice  OFFSET {tope} (no borra)",
          lambda: con.execute(PODA_B, (tope,)))
    con.close()

print("\n=== C) Regimen estacionario: cada escritura borra UNA fila ===")
print("    Se cronometra SOLO la poda, no el INSERT que la precede.\n")

for etiqueta, sql, parametros in (
    ("(a) MIN sobre subconsulta", PODA_A, (LIMITE,)),
    ("(b) OFFSET sobre el indice", PODA_B, (LIMITE,)),
    ("(c) borrar solo la mas vieja", PODA_C, ()),
):
    con = db(LIMITE)
    tiempos = []
    for _ in range(1000):
        con.execute(INSERT, fila())
        t0 = time.perf_counter()
        con.execute(sql, parametros)
        tiempos.append(time.perf_counter() - t0)
    total = con.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    media = sum(tiempos) / len(tiempos) * 1e6
    print(f"  {etiqueta:<50} {media:11.2f} us/op   -> quedan {total} filas", flush=True)
    con.close()

print("\n=== D) SELECT COUNT(*), que GET /history hace en CADA lectura ===\n")

for filas in (1_000, 10_000, 50_000):
    con = db(filas)
    bench(f"SELECT COUNT(*) sobre {filas} filas",
          lambda: con.execute("SELECT COUNT(*) FROM history").fetchone(), n=500)
    con.close()
