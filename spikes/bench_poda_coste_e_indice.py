"""Mide el coste de la poda antes de decidir donde se ejecuta (#103).

Tres preguntas, en este orden:

A) .Anade el DELETE un fsync? Si viaja en el commit que ya se estaba haciendo,
   la escritura completa NO deberia cambiar de orden de magnitud. Si anadiera
   una sincronizacion propia, se duplicaria (~164 -> ~328 ms) y se veria a
   simple vista incluso con ruido.

B) .Cuanto cuesta la CONSULTA de poda aislada, sin el fsync que la envuelve?

C) .Escala con el tamano de la tabla? Es lo que decide si hace falta indice.

Sobre el metodo de C: en regimen estacionario cada INSERT borra exactamente UNA
fila, asi que el coste recurrente es 'buscar que borrar' (escala con el tamano)
mas 'liberar una fila' (constante). Midiendo una poda que NO encuentra nada se
aisla la parte que escala, y ademas no muta la tabla entre iteraciones.

RESULTADOS (2026-08-14, WSL2 ext4 sobre VHD, Python 3.12.3 / SQLite 3.45.1)

  A) escritura completa, synchronous por defecto
       INSERT solo (referencia)                          241.5 ms
       INSERT + poda cantidad [no borra nada]            229.0 ms
       INSERT + poda cantidad [borra 1 por escritura]    163.8 ms
       INSERT + poda antiguedad                          189.7 ms
       INSERT + las dos podas                            202.1 ms

  B/C) consulta aislada, sin fsync
                                     1 000      10 000      50 000 filas
       poda ANTIGUEDAD sin indice   2 374 us   11 113 us   54 595 us
       poda ANTIGUEDAD con indice     0.99 us     1.02 us     0.97 us

  D) coste del indice al INSERTAR
       sin indice en created_at    14.29 us
       con indice en created_at    13.91 us

CONCLUSIONES

A) NO SIRVE para medir el sobrecoste, y hay que decirlo: podar sale mas rapido
   que no podar, lo cual es imposible como efecto real. El ruido del fsync en
   WSL2 (+-40 %) se come la senal y con n=40 no se promedia. Insistir con mas
   iteraciones tampoco valdria: la diferencia buscada (~1.6 ms) es el 1 % de una
   escritura con fsync y nunca se resolveria contra ese ruido.

   Lo unico que si sobrevive es la lectura gruesa, que era la pregunta: ninguna
   variante se acerca al DOBLE, asi que el DELETE no anade un fsync propio y
   viaja en el commit que el INSERT ya estaba pagando.

B/C) El indice en created_at es el hallazgo: ~2400x mas rapido a 1000 filas, y
   CONSTANTE en vez de lineal. Sin el, `created_at < ?` recorre la tabla entera.

D) Y no se paga al escribir: la version CON indice sale mas rapida que la que no
   lo tiene, o sea que la diferencia esta por debajo del ruido de medida. Es la
   pregunta que no se le hizo a WAL en #102.

OJO: la parte de 'poda por CANTIDAD' de este banco tiene un FALLO DE DISENO —se
paso LIMIT = filas + 10, haciendo crecer el limite junto con la tabla— asi que
sus numeros no miden lo que dicen. Rehecho en bench_poda_limite_fijo_y_count.py.
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

# Buscar el id de la N-esima mas nueva y borrar por debajo. NO vale
# `MAX(id) - N`: en cuanto la poda ha borrado alguna vez los ids tienen huecos.
DELETE_CANTIDAD = """
DELETE FROM history
WHERE id < (SELECT MIN(id) FROM (SELECT id FROM history ORDER BY id DESC LIMIT ?))
"""
DELETE_ANTIGUEDAD = "DELETE FROM history WHERE created_at < ?"

PAYLOAD = json.dumps({"signals": [{"n": f"s{i}", "d": "x" * 400} for i in range(5)]})
AHORA = datetime.now(timezone.utc)


def fila(dias_atras=0):
    marca = (AHORA - timedelta(days=dias_atras)).isoformat()
    return (marca, "analysis", "api", "Un titular", None, "clickbait", "ok", PAYLOAD)


def nueva_db(filas=0, dias_de_antiguedad=0, indice=False, rapida=True):
    """Base recien creada, opcionalmente poblada y con indice en created_at."""
    ruta = Path(tempfile.mkdtemp()) / "history.db"
    con = sqlite3.connect(ruta)
    if rapida:
        con.execute("PRAGMA synchronous=OFF")
    con.execute(ESQUEMA)
    if indice:
        con.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON history(created_at)")
    if filas:
        # Repartidas en el tiempo, para que la poda por antiguedad tenga sentido.
        with con:
            con.executemany(
                INSERT,
                [fila(dias_atras=(i * dias_de_antiguedad) // max(filas, 1)) for i in range(filas)],
            )
    con.close()
    return ruta


def bench(etiqueta, fn, n, unidad="ms"):
    fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    por_op = (time.perf_counter() - t0) / n
    valor = por_op * 1e3 if unidad == "ms" else por_op * 1e6
    print(f"  {etiqueta:<56} {valor:10.3f} {unidad}/op   (n={n})", flush=True)
    return valor


print(f"Python {sys.version.split()[0]} | SQLite {sqlite3.sqlite_version}", flush=True)

# ------------------------------------------------------------------ A
print("\n=== A) .Anade el DELETE un fsync? (synchronous por defecto) ===", flush=True)
print("    Si lo anadiera, se veria un salto de ~164 a ~328 ms.\n", flush=True)

LIMITE = 1000
N_A = 40


def escritura(ruta, podar_cantidad=False, podar_antiguedad=False):
    def hacer():
        con = sqlite3.connect(ruta)
        con.row_factory = sqlite3.Row
        con.execute(ESQUEMA)
        try:
            with con:
                con.execute(INSERT, fila())
                if podar_cantidad:
                    con.execute(DELETE_CANTIDAD, (LIMITE,))
                if podar_antiguedad:
                    con.execute(DELETE_ANTIGUEDAD, ((AHORA - timedelta(days=30)).isoformat(),))
        finally:
            con.close()

    return hacer


base = bench("INSERT solo (referencia)", escritura(nueva_db(rapida=False)), N_A)

# Tabla por debajo del limite: la poda por cantidad no encuentra nada que borrar.
r = nueva_db(filas=100, rapida=False)
bench("INSERT + poda cantidad  [no borra nada]", escritura(r, podar_cantidad=True), N_A)

# Regimen estacionario: la tabla esta en el limite, cada INSERT borra 1 fila.
r = nueva_db(filas=LIMITE, rapida=False)
estacionario = bench("INSERT + poda cantidad  [borra 1 por escritura]",
                     escritura(r, podar_cantidad=True), N_A)

r = nueva_db(filas=LIMITE, dias_de_antiguedad=60, rapida=False)
bench("INSERT + poda antiguedad [borra las de +30 dias]",
      escritura(r, podar_antiguedad=True), N_A)

r = nueva_db(filas=LIMITE, dias_de_antiguedad=60, rapida=False)
ambas = bench("INSERT + LAS DOS podas", escritura(r, podar_cantidad=True, podar_antiguedad=True), N_A)

print(f"\n  => sobrecoste de la poda en regimen estacionario: "
      f"{estacionario - base:+.1f} ms sobre {base:.1f} ms", flush=True)
print(f"  => con las dos podas:                             "
      f"{ambas - base:+.1f} ms", flush=True)
print("  => si estos deltas son ruido y no ~164 ms, el DELETE NO anade fsync", flush=True)

# ------------------------------------------------------------------ B y C
print("\n=== B/C) Coste de la CONSULTA aislada, y como escala ===", flush=True)
print("    Sin fsync. La poda no encuentra nada, para aislar la busqueda.\n", flush=True)

VIEJO = (AHORA - timedelta(days=3650)).isoformat()

for filas in (1_000, 10_000, 50_000):
    print(f"  --- tabla de {filas:,} filas ---".replace(",", " "), flush=True)

    ruta = nueva_db(filas=filas, dias_de_antiguedad=60)
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA synchronous=OFF")
    bench(f"poda por CANTIDAD (id + subconsulta)",
          lambda: con.execute(DELETE_CANTIDAD, (filas + 10,)), 2000, unidad="us")
    bench(f"poda por ANTIGUEDAD sin indice en created_at",
          lambda: con.execute(DELETE_ANTIGUEDAD, (VIEJO,)), 200, unidad="us")
    con.close()

    ruta = nueva_db(filas=filas, dias_de_antiguedad=60, indice=True)
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA synchronous=OFF")
    bench(f"poda por ANTIGUEDAD CON indice en created_at",
          lambda: con.execute(DELETE_ANTIGUEDAD, (VIEJO,)), 2000, unidad="us")
    con.close()

# ------------------------------------------------------------------ D
print("\n=== D) .Y el coste del indice al ESCRIBIR? ===", flush=True)
print("    Un indice acelera la lectura y encarece cada insercion: hay que ver", flush=True)
print("    si lo que ahorra en C lo devuelve aqui.\n", flush=True)

for indice in (False, True):
    ruta = nueva_db(filas=1000, indice=indice)
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA synchronous=OFF")
    bench(f"INSERT con indice en created_at = {indice}",
          lambda: con.execute(INSERT, fila()), 2000, unidad="us")
    con.close()
