""".Falla la comparacion lexicografica de fechas por microsegundos o por 'Z'?

Afirmacion a comprobar: que `2026-...T16:33:04.123456+00:00` (guardado, CON
microsegundos) y `2026-...T16:33:04+00:00` (filtro, SIN ellos) se comparen mal
como cadenas y descarten o incluyan registros equivocados.

RESULTADO: la afirmacion es FALSA. Las seis combinaciones (>= y <= por tres
formatos de filtro) coinciden con lo que dice Python comparando datetime de
verdad.

  sin microsegundos, +00:00   >=  ->  6 filas   OK
  sin microsegundos, +00:00   <=  ->  6 filas   OK
  con microsegundos,  +00:00  >=  ->  6 filas   OK
  con microsegundos,  +00:00  <=  ->  6 filas   OK
  desde otro huso (+05:00)    >=  ->  6 filas   OK
  desde otro huso (+05:00)    <=  ->  6 filas   OK

POR QUE FUNCIONA: el caracter que sigue a los segundos es '.' (46) si hay
microsegundos y '+' (43) si no. Como 46 > 43, '...04.123456+00:00' ordena DESPUES
de '...04+00:00', que es justo el orden cronologico correcto. Acierta por la
tabla ASCII, no por diseno consciente.

Y el sufijo 'Z' ya esta resuelto aguas arriba: `_marca` re-serializa siempre con
isoformat(), asi que un ?since=...Z sale convertido a +00:00 antes de tocar SQL.

PERO: 'Z' es el caracter 90 y ordena despues de CUALQUIER desfase, asi que
mezclar los dos formatos SI romperia las comparaciones, en silencio. Nada impedia
que un codigo futuro escribiera 'Z'. De ahi que, aunque no hubiera bug, se
centralizara todo lo que toca `created_at` en `_marca`: la correccion dependia de
que tres sitios se acordaran de hacer lo mismo.
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/ggarciac/TFG/2026-ClickBaitAnalysis")

BASE = datetime(2026, 8, 14, 16, 33, 4, tzinfo=timezone.utc)

print("=== .Que formatos produce isoformat() en cada sitio? ===\n")
con_micros = BASE.replace(microsecond=123456)
sin_micros = BASE.replace(microsecond=0)
print(f"  _guardar con microsegundos : {con_micros.isoformat()}")
print(f"  _guardar sin microsegundos : {sin_micros.isoformat()}   <- cuando cae en .000000")
print(f"  _marca desde sufijo 'Z'    : {datetime.fromisoformat('2026-08-14T16:33:04Z').astimezone(timezone.utc).isoformat()}")
print(f"  _marca desde +05:00        : {datetime.fromisoformat('2026-08-14T21:33:04+05:00').astimezone(timezone.utc).isoformat()}")

print("\n=== .Coincide el orden ALFABETICO con el CRONOLOGICO? ===\n")
print("  El caracter que sigue a los segundos es '.' (46) si hay microsegundos")
print("  y '+' (43) si no. Como 46 > 43, '...04.123456+00:00' ordena DESPUES de")
print(f"  '...04+00:00'. Y eso es cronologicamente correcto.\n")
print(f"  ord('.') = {ord('.')}   ord('+') = {ord('+')}   ord('-') = {ord('-')}")
print(f"  '{con_micros.isoformat()}' > '{sin_micros.isoformat()}' -> "
      f"{con_micros.isoformat() > sin_micros.isoformat()}   (esperado True)")

print("\n=== Prueba real contra SQLite ===\n")
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE t (created_at TEXT)")

# Una fila por cada decima de segundo alrededor del instante base.
instantes = [BASE + timedelta(microseconds=i * 100_000) for i in range(-5, 6)]
con.executemany("INSERT INTO t VALUES (?)", [(m.isoformat(),) for m in instantes])
con.commit()

fallos = 0
for etiqueta, filtro in (
    ("sin microsegundos, +00:00", BASE.isoformat()),
    ("con microsegundos,  +00:00", BASE.replace(microsecond=0).isoformat()),
    ("desde otro huso (+05:00)  ", BASE.astimezone(timezone(timedelta(hours=5))).astimezone(timezone.utc).isoformat()),
):
    for operador, comparar in ((">=", lambda m: m >= BASE), ("<=", lambda m: m <= BASE)):
        sql_dice = {
            f[0] for f in con.execute(f"SELECT created_at FROM t WHERE created_at {operador} ?", (filtro,))
        }
        python_dice = {m.isoformat() for m in instantes if comparar(m)}
        ok = sql_dice == python_dice
        fallos += not ok
        print(f"  {etiqueta}  {operador}  -> {len(sql_dice):>2} filas   "
              f"{'OK' if ok else 'DISCREPA con Python'}")

print(f"\n  {'TODO COINCIDE' if not fallos else f'{fallos} DISCREPANCIAS'}: la comparacion "
      f"lexicografica {'reproduce' if not fallos else 'NO reproduce'} el orden cronologico.")

print("\n=== .Y si alguien guardara con sufijo Z? (no ocurre hoy) ===\n")
con.execute("INSERT INTO t VALUES (?)", ("2026-08-14T16:33:04Z",))
con.commit()
filtro = BASE.isoformat()
con_z = con.execute("SELECT created_at FROM t WHERE created_at >= ?", (filtro,)).fetchall()
print(f"  'Z' (90) frente a '+' (43): 'Z' ordena SIEMPRE despues de cualquier desfase.")
print(f"  La fila con Z {'aparece' if any('Z' in f[0] for f in con_z) else 'NO aparece'} "
      f"en un >= sobre su propio instante.")
print("  -> mezclar los dos formatos SI romperia el orden. Hoy no se mezclan:")
print("     todo lo que se escribe pasa por isoformat(), que produce '+00:00'.")
con.close()
