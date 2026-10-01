"""#189 (2026-09-26) - La aceptación de `/chat` en la máquina 1, a través de Caddy.

Habla con la API desplegada como lo hará la pantalla de #191 —por HTTPS, con el
prefijo `/api` que quita Caddy, y sondeando `GET /chat/{id}` cada 2 s, que es
lo decidido— y anota lo que pasa. Tres partes, que lanza `chat_maquina1.sh`
alrededor de una sesión de GPU:

- `cerrada-antes` y `cerrada-despues`: sin sesión, `GET /agent` tiene que decir
  `unreachable` y `POST /chat` responder 503 con el mismo motivo (R6.14).
- `abierta`: con la sesión y su túnel,
  - `GET /agent` dice `available`;
  - una conversación sencilla y la más larga de #188 (una noticia del NYT y su
    análisis completo: 5.765–5.842 tokens de prompt);
  - la más larga otra vez, con el historial EN EL TOPE (`chat_max_history_chars`,
    4.000 caracteres): es la medida que decide el tope, con una regla fijada
    antes de medir — por debajo de 7.500 tokens de los 8.192 de la ventana se
    queda; si no, se baja en proporción;
  - y dos a la vez, para ver la segunda en `queued`.

De cada conversación: los estados que se vieron, cuántos sondeos, si alguno dio
429, el final, las herramientas y el `prompt_tokens` de cada vuelta del modelo.

El certificado es el autofirmado de #165, así que no se verifica: aquí se
comprueba la aplicación, no el certificado.

Ejecutar desde la raíz (normalmente lo lanza `spikes/chat_maquina1.sh`):
  .venv/bin/python spikes/chat_maquina1.py cerrada-antes|abierta|cerrada-despues
El JSON va a CHAT_MAQUINA1_JSON (por defecto /tmp/chat_maquina1.json), una
clave por parte.
"""

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BASE = os.environ.get("CHAT_BASE", "https://gongarcia.tfg.etsii.urjc.es/api")
SALIDA = Path(os.environ.get("CHAT_MAQUINA1_JSON", "/tmp/chat_maquina1.json"))
SONDEO_S = 2.0  # el intervalo decidido para la pantalla de #191
TOPE_HISTORIAL = 4000  # `chat_max_history_chars` del despliegue
ESPERA_MAX_S = 400.0

SENCILLA = "¿Es clickbait el titular 'You Won't Believe What This Dog Did Next'?"
# La conversación que más ventana ocupó en #188 («encadena-nyt»).
LARGA = (
    "Busca una noticia del New York Times sobre inteligencia artificial y dime "
    "si su titular es clickbait."
)

# Turnos anteriores con la forma de una conversación de verdad: una pregunta y
# una narración con cifras, pistas y titulares en inglés, que son lo que más
# tokens gasta por carácter. Se repiten hasta llenar el tope EXACTO.
_TITULARES = [
    "Scientists Discover New Species in the Deep Ocean",
    "10 Amazing Things You Won't Believe About Cats",
    "Federal Reserve Holds Interest Rates Steady",
    "This Simple Trick Will Shock You",
    "Top 5 Secrets Finally Revealed",
]
_NARRACION = (
    "He consultado cuatro señales sobre «{titular}». El detector léxico encontró "
    "{pistas} pistas de las listas de Chakraborty, entre ellas hipérboles y "
    "referencias hacia delante. El modelo lineal le da una probabilidad de 0,{p} "
    "de ser clickbait, con el umbral en 0,5, y la palabra que más pesa aporta "
    "0,{peso}. La caja negra lo etiqueta con una confianza de 0,{c}. La "
    "incoherencia no se pudo medir porque no me diste el cuerpo de la noticia, "
    "así que la dimensión de engaño queda sin evaluar. El tono es neutro (0,71). "
    "Las señales de forma {acuerdo}, y el veredicto de las herramientas es "
    "«{veredicto}»."
)


def historial_en_el_tope(tope: int = TOPE_HISTORIAL) -> list[dict[str, str]]:
    """Turnos de usuario y asistente que suman EXACTAMENTE `tope` caracteres."""
    turnos: list[dict[str, str]] = []
    total = 0
    indice = 0
    while total < tope:
        titular = _TITULARES[indice % len(_TITULARES)]
        pregunta = f"¿Es clickbait el titular '{titular}'?"
        narracion = _NARRACION.format(
            titular=titular,
            pistas=indice % 4,
            p=163 + 97 * indice,
            peso=41 + 13 * indice,
            c=88 + indice,
            acuerdo="coinciden" if indice % 2 else "discrepan",
            veredicto="factual" if indice % 2 else "ambiguous",
        )
        for rol, texto in (("user", pregunta), ("assistant", narracion)):
            texto = texto[: tope - total]
            if texto:
                turnos.append({"role": rol, "content": texto})
                total += len(texto)
        indice += 1
    return turnos


async def conversar(
    cliente: httpx.AsyncClient,
    mensaje: str,
    historial: list[dict[str, str]] | None = None,
    retraso_s: float = 0.0,
) -> dict[str, Any]:
    """Una conversación entera, sondeando como la pantalla."""
    historial = historial or []
    await asyncio.sleep(retraso_s)
    inicio = time.perf_counter()
    respuesta = await cliente.post(
        "/chat", json={"message": mensaje, "history": historial}
    )
    fila: dict[str, Any] = {
        "mensaje": mensaje,
        "historial_caracteres": sum(len(turno["content"]) for turno in historial),
        "post": respuesta.status_code,
        "post_s": round(time.perf_counter() - inicio, 3),
    }
    if respuesta.status_code != 202:
        fila["detalle"] = respuesta.json().get("detail")
        return fila

    trabajo_id = respuesta.json()["id"]
    estados: list[str] = []
    sondeos = rechazos = 0
    trabajo: dict[str, Any] = {}
    while time.perf_counter() - inicio < ESPERA_MAX_S:
        await asyncio.sleep(SONDEO_S)
        leido = await cliente.get(f"/chat/{trabajo_id}")
        sondeos += 1
        if leido.status_code == 429:
            rechazos += 1
            continue
        trabajo = leido.json()
        if not estados or estados[-1] != trabajo["status"]:
            estados.append(trabajo["status"])
        if trabajo["status"] == "done":
            break

    resultado = trabajo.get("result") or {}
    pasos = trabajo.get("steps", [])
    vueltas = [paso for paso in pasos if paso["kind"] == "model"]
    fila.update(
        {
            "estados": estados,
            "sondeos": sondeos,
            "rechazos_429": rechazos,
            "reloj_s": round(time.perf_counter() - inicio, 1),
            "final": resultado.get("status"),
            "detalle": resultado.get("detail"),
            "vueltas": resultado.get("rounds"),
            "agente_s": round(resultado.get("total_s", 0.0), 1),
            "herramientas": [
                [paso["name"], paso["status"]]
                for paso in pasos
                if paso["kind"] == "tool"
            ],
            "prompt_tokens": [paso["metrics"]["prompt_tokens"] for paso in vueltas],
            # Añadidos tras la primera ejecución, que no los guardaba: sin ellos
            # no se pudo saber si una narración de 48,5 s escribió más o fue
            # más lenta. El desglose de esa vez salió del log de la API.
            "output_tokens": [paso["metrics"]["output_tokens"] for paso in vueltas],
            "vuelta_s": [round(paso["metrics"]["total_s"], 1) for paso in vueltas],
            "herramienta_s": [
                round(paso["duration_s"], 2) for paso in pasos if paso["kind"] == "tool"
            ],
            "carga_s": [round(paso["metrics"]["load_s"], 1) for paso in vueltas],
            "respuesta": resultado.get("answer", "")[:400],
        }
    )
    return fila


def _imprimir(nombre: str, fila: dict[str, Any]) -> None:
    if fila["post"] != 202:
        print(
            f"  {nombre:26} POST {fila['post']} en {fila['post_s']} s: {fila.get('detalle')}"
        )
        return
    tokens = [t for t in fila["prompt_tokens"] if t is not None]
    print(
        f"  {nombre:26} POST 202 en {fila['post_s']} s · {' → '.join(fila['estados'])} · "
        f"{fila['final']} · {fila['vueltas']} vueltas · agente {fila['agente_s']} s · "
        f"reloj {fila['reloj_s']} s · {fila['sondeos']} sondeos, {fila['rechazos_429']} con 429 · "
        f"prompt_tokens {fila['prompt_tokens']} (máx {max(tokens) if tokens else '—'}) · "
        f"por vuelta {fila['vuelta_s']} s y {fila['output_tokens']} tokens de salida · "
        f"herramientas en {fila['herramienta_s']} s · "
        f"historial {fila['historial_caracteres']} car. · herramientas {fila['herramientas']}"
    )


async def cerrada(cliente: httpx.AsyncClient) -> dict[str, Any]:
    agente = (await cliente.get("/agent")).json()
    inicio = time.perf_counter()
    respuesta = await cliente.post("/chat", json={"message": SENCILLA})
    fila = {
        "availability": agente["availability"],
        "post": respuesta.status_code,
        "post_s": round(time.perf_counter() - inicio, 3),
        "detalle": respuesta.json().get("detail"),
    }
    print(f"  GET /agent: {agente['availability']}")
    print(f"  POST /chat: {fila['post']} en {fila['post_s']} s · {fila['detalle']}")
    print(
        f"  mismo motivo en las dos: {fila['detalle'] == agente['availability']['detail']}"
    )
    return fila


async def abierta(cliente: httpx.AsyncClient) -> dict[str, Any]:
    # El túnel lo abre `gpu-sesion` a la vez que Ollama: se espera a que la API
    # lo vea, como mucho un minuto.
    for _ in range(30):
        agente = (await cliente.get("/agent")).json()
        if agente["availability"]["status"] == "available":
            break
        await asyncio.sleep(2)
    print(
        f"  GET /agent: {agente['availability']} · ficha {agente['model_card']['model_id']}"
        f" · prompt {agente['prompt']['name']}"
    )
    registro: dict[str, Any] = {"agent": agente["availability"]}
    if agente["availability"]["status"] != "available":
        print("  EL ASISTENTE NO ESTÁ DISPONIBLE: no se conversa.")
        return registro

    for nombre, mensaje, historial in (
        ("sencilla", SENCILLA, None),
        ("larga", LARGA, None),
        ("larga con historial", LARGA, historial_en_el_tope()),
    ):
        registro[nombre] = await conversar(cliente, mensaje, historial)
        _imprimir(nombre, registro[nombre])

    primera, segunda = await asyncio.gather(
        conversar(cliente, SENCILLA),
        conversar(
            cliente, "¿Es clickbait 'Top 5 Secrets Finally Revealed'?", retraso_s=0.5
        ),
    )
    registro["a la vez, primera"], registro["a la vez, segunda"] = primera, segunda
    _imprimir("a la vez, primera", primera)
    _imprimir("a la vez, segunda", segunda)
    return registro


async def main(parte: str) -> dict[str, Any]:
    print(f"== {parte} · {datetime.now(UTC).isoformat(timespec='seconds')} · {BASE}")
    # Autofirmado (#165): se comprueba la aplicación, no el certificado.
    async with httpx.AsyncClient(base_url=BASE, verify=False, timeout=30) as cliente:
        return await (abierta(cliente) if parte == "abierta" else cerrada(cliente))


if __name__ == "__main__":
    PARTES = ("cerrada-antes", "abierta", "cerrada-despues")
    if len(sys.argv) != 2 or sys.argv[1] not in PARTES:
        sys.exit(f"Uso: chat_maquina1.py {'|'.join(PARTES)}")
    parte = sys.argv[1]
    medida = asyncio.run(main(parte))
    guardado = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    guardado[parte] = {
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        **medida,
    }
    SALIDA.write_text(
        json.dumps(guardado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
