"""Cierre de `v0.7` (2026-10-07) - ¿Responde en vivo lo que se publica?

El tercer criterio para etiquetar una versión (README, «Releases») es que las
herramientas respondan en vivo. Esto lo comprueba en la máquina 1, por la API
pública y a través de Caddy, como lo vería cualquiera:

1. qué commit sirve el clon de la máquina 1 (una sola conexión SSH);
2. el catálogo: cuántas herramientas publica y la ficha del lineal;
3. cada herramienta, ejecutada con argumentos mínimos, con su estado y un
   resumen de lo que devuelve;
4. el veredicto de #124: un titular sobrio con un cuerpo que no le corresponde
   da `ambiguous` desde #124 (antes, `deceptive`). Queda en el historial de
   producción, como cualquier análisis;
5. el agente: su disponibilidad, que con la sesión de GPU cerrada es «no».

Las rutas caras admiten 10 peticiones por minuto y cliente (#169): ante un 429
se espera lo que diga `Retry-After` y se repite una vez. El certificado es
autofirmado (#165), así que no se verifica.

Ejecutar desde la raíz:

    .venv/bin/python spikes/produccion_en_vivo.py
"""

import json
import subprocess
import time
from datetime import datetime

import httpx

BASE = "https://gongarcia.tfg.etsii.urjc.es/api"
MAQUINA_1 = "vmuser@193.147.60.40"

TITULAR = "10 Secrets Doctors Won't Tell You... Are You Ready?"
CUERPO = "A small study in mice found modest effects of the diet after eight weeks."
ARGUMENTOS = {
    "detect_clickbait": {"headline": TITULAR},
    "detect_clickbait_lexical": {"headline": TITULAR},
    "detect_clickbait_linear": {"headline": TITULAR},
    "detect_clickbait_incoherence": {"headline": TITULAR, "content": CUERPO},
    "analyze_sentiment": {"text": TITULAR},
    "analyze_headline": {"headline": TITULAR, "content": CUERPO},
    "describe_models": {},
    "get_nyt_news": {"topic": "climate"},
    "get_guardian_news": {"topic": "climate"},
    "get_alerts": {"state": "CA"},
    "get_forecast": {"latitude": 40.7128, "longitude": -74.006},
    "health_check": {},
}
# #124: la forma dice «no» por unanimidad y el engaño «sí».
CASO_124 = {
    "headline": "Federal Reserve raises interest rates by a quarter point",
    "content": "The local football team won the championship after a dramatic "
    "penalty shootout on Sunday night.",
}


def pedir(cliente: httpx.Client, metodo: str, ruta: str, **opciones) -> httpx.Response:
    respuesta = cliente.request(metodo, f"{BASE}{ruta}", **opciones)
    if respuesta.status_code == 429:
        espera = int(respuesta.headers.get("retry-after", "60"))
        print(f"     (429: espero {espera} s)", flush=True)
        time.sleep(espera)
        respuesta = cliente.request(metodo, f"{BASE}{ruta}", **opciones)
    return respuesta


def resumen(nombre: str, datos: dict | None) -> str:
    if not datos:
        return "-"
    if nombre == "detect_clickbait_linear":
        rasgos = [rasgo for rasgo, _ in datos.get("top_cues", [])[:5]]
        return f"p {datos.get('probability', 0):.3f} · {rasgos}"
    if nombre == "detect_clickbait_lexical":
        pistas = [pista["cue"] for pista in datos.get("matches", [])]
        return f"{datos.get('score')} pistas {pistas} · umbral {datos.get('threshold')}"
    if nombre == "analyze_headline":
        return f"veredicto {datos.get('verdict')}"
    return json.dumps(datos, ensure_ascii=False)[:140]


def main() -> None:
    servido = subprocess.run(
        ["ssh", "-n", "-o", "BatchMode=yes", MAQUINA_1,
         "cd ~/2026-ClickBaitAnalysis && git rev-parse --short HEAD"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    print(f"== {datetime.now().astimezone().isoformat(timespec='seconds')} · la máquina 1 sirve {servido}")

    with httpx.Client(verify=False, timeout=120) as cliente:
        catalogo = pedir(cliente, "GET", "/tools").json()
        nombres = sorted(herramienta["name"] for herramienta in catalogo["tools"])
        print(f"\n== catálogo: {len(nombres)} herramientas · degradado: {catalogo.get('degraded')}")
        lineal = next(
            herramienta for herramienta in catalogo["tools"]
            if herramienta["name"] == "detect_clickbait_linear"
        )
        print(f"   ficha del lineal: {(lineal.get('model_card') or {}).get('name')}")

        print(f"\n== cada herramienta, con «{TITULAR}»")
        for nombre in nombres:
            argumentos = ARGUMENTOS.get(nombre)
            if argumentos is None:
                print(f"   {nombre:30} SIN ARGUMENTOS PREVISTOS: no se ejecuta")
                continue
            inicio = time.perf_counter()
            respuesta = pedir(
                cliente, "POST", f"/tools/{nombre}/execute", json={"arguments": argumentos}
            )
            segundos = time.perf_counter() - inicio
            if respuesta.status_code != 200:
                print(f"   {nombre:30} HTTP {respuesta.status_code} · {respuesta.text[:120]}")
                continue
            cuerpo = respuesta.json()
            detalle = f" · {cuerpo['detail'][:100]}" if cuerpo.get("detail") else ""
            print(
                f"   {nombre:30} {cuerpo['status']:5} {segundos:5.1f} s · "
                f"{resumen(nombre, cuerpo.get('data'))}{detalle}",
                flush=True,
            )

        print("\n== el caso de #124")
        analisis = pedir(cliente, "POST", "/analyze", json=CASO_124).json()["analysis"]
        dimensiones = {
            dimension["dimension"]: dimension["is_clickbait"]
            for dimension in analisis["dimensions"]
        }
        print(f"   veredicto {analisis['verdict']} · dimensiones {dimensiones}")

        agente = pedir(cliente, "GET", "/agent").json()["availability"]
        print(f"\n== el agente: {agente['status']} · {agente['detail']}")


if __name__ == "__main__":
    main()
