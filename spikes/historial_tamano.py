"""#209 (2026-10-03) - Cuánto ocupa en `sessionStorage` un intercambio del asistente.

La pantalla del asistente guarda cada pregunta con su conversación entera —la
traza con los resultados de las herramientas, para volver a pintar las
tarjetas al recargar— y le pone un tope en caracteres de JSON. Para fijarlo
hace falta saber cuánto ocupa un intercambio, y se mide con las conversaciones
que guardó #192 en `spikes/fidelidad/`: las del corpus y las de cada
condición comparada, con los pasos tal como los produce el agente.

Lo que sirve la API no es exactamente eso: a cada paso de señal le añade su
tarjeta (`signal`). Aquí se añade con `senal_de`, la misma función que usa
`api/chat.py` al servir `GET /chat/{id}`, y el intercambio se monta con la
forma de `Intercambio` (`frontend/src/app/asistente/conversacion.ts`). Se mide
la longitud del JSON sin espacios, que es lo que escribe `JSON.stringify`, en
caracteres, que es como cuentan los navegadores el límite. (Python cuenta
puntos de código y el navegador unidades UTF-16: sólo difieren en los
caracteres fuera del plano básico, como los emojis.)

La regla, fijada ANTES de medir (decidida por el autor): el tope es de
1.000.000 de caracteres, una quinta parte de los ~5 MB que dan los navegadores
por origen, y se queda si caben al menos 20 intercambios de tamaño mediano.

Ejecutar desde la raíz: .venv/bin/python spikes/historial_tamano.py
"""

import json
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.analysis.orchestrator import senal_de  # noqa: E402

DATOS = RAIZ / "spikes" / "fidelidad"
FICHEROS = ["corpus.json", *sorted(p.name for p in DATOS.glob("comparacion-*.json"))]

TOPE = 1_000_000
MINIMO_DE_INTERCAMBIOS = 20


def _como_la_api(paso: dict) -> dict:
    """El paso tal como lo publica `GET /chat/{id}` (`api/chat.py`, `_publicar`)."""
    if paso["kind"] == "model":
        return paso
    senal = senal_de(paso["name"], paso["data"]) if paso["status"] == "ok" else None
    return {**paso, "signal": senal.model_dump(mode="json") if senal else None}


def _intercambio(conversacion: dict) -> dict:
    """Lo que guardaría la pantalla: la forma de `Intercambio`, terminado."""
    vueltas = conversacion.get("vueltas")
    return {
        "pregunta": conversacion["consulta"],
        "id": "0" * 32,  # 16 bytes aleatorios, en hexadecimal (#189)
        "trabajo": {
            "id": "0" * 32,
            "status": "done",
            "created_at": "2026-10-03T10:00:00.000000Z",
            "steps": [_como_la_api(paso) for paso in conversacion["pasos"]],
            "result": {
                "status": conversacion["estado"],
                "answer": conversacion.get("respuesta") or "",
                "detail": conversacion.get("detalle"),
                "rounds": len(vueltas) if isinstance(vueltas, list) else vueltas,
                "total_s": conversacion.get("total_s"),
            },
        },
        "error": None,
        "enviadaEl": 1_759_485_600_000,
        "leidaEl": 1_759_485_612_345,
    }


def _caracteres(valor: object) -> int:
    return len(json.dumps(valor, ensure_ascii=False, separators=(",", ":")))


def _miles(numero: float) -> str:
    """12.345, con el punto de los miles en castellano."""
    return f"{numero:,.0f}".replace(",", ".")


def main() -> None:
    medidas = []
    for nombre in FICHEROS:
        for conversacion in json.loads((DATOS / nombre).read_text())["conversaciones"]:
            intercambio = _intercambio(conversacion)
            medidas.append(
                (
                    _caracteres(intercambio),
                    nombre,
                    conversacion["consulta"],
                    sorted(
                        {
                            p["name"]
                            for p in conversacion["pasos"]
                            if p["kind"] == "tool"
                        }
                    ),
                )
            )

    tamanos = sorted(medida[0] for medida in medidas)
    mediana = statistics.median(tamanos)
    p95 = tamanos[int(0.95 * (len(tamanos) - 1))]
    print(f"Intercambios medidos: {len(tamanos)} ({', '.join(FICHEROS)})")
    print(
        f"Caracteres por intercambio: mínimo {_miles(tamanos[0])} · mediana {_miles(mediana)}"
        f" · p95 {_miles(p95)} · máximo {_miles(tamanos[-1])}"
    )

    print("\nLos tres más grandes:")
    for caracteres, nombre, consulta, herramientas in sorted(medidas, reverse=True)[:3]:
        print(
            f"  {_miles(caracteres):>7} · {nombre} · {consulta[:60]!r} · {', '.join(herramientas)}"
        )

    caben_medianos = int(TOPE // mediana)
    caben_maximos = int(TOPE // tamanos[-1])
    print(
        f"\nCon un tope de {_miles(TOPE)} caracteres caben {caben_medianos} intercambios"
        f" medianos y {caben_maximos} del más grande."
    )
    veredicto = (
        "SE QUEDA" if caben_medianos >= MINIMO_DE_INTERCAMBIOS else "NO SE QUEDA"
    )
    print(f"Regla (al menos {MINIMO_DE_INTERCAMBIOS} medianos): {veredicto}")


if __name__ == "__main__":
    main()
