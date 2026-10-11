"""#236 (2026-10-08) - ¿Sirve la vía remota de Hugging Face con la cuenta del proyecto?

El 7 oct 2026 Hugging Face retiró el crédito mensual incluido de las cuentas
gratuitas: en https://huggingface.co/docs/inference-providers/pricing, la fila
«Free Users» pasó de «$0.10, subject to change» a «None»
(huggingface/hub-docs#2865). Esa misma tarde la vía remota empezó a responder
402 al tono. Este guion lo repite, en tres partes:

1. el tipo de cuenta del token (`isPro`, `canPay` y el papel del token), sin
   el nombre de la cuenta ni el token;
2. el código HTTP que da `hf-inference` a los tres modelos que han pasado por
   la vía remota —el tono, el zero-shot de #159 (BART) y la dedicada—, con el
   principio del cuerpo del proveedor;
3. y lo que devuelve `HFClient`, el cliente de producción, que es lo que leería
   la tarjeta de la señal con `nlp_backend=remote`.

Llama a Hugging Face de verdad, con el `HF_TOKEN` del `.env`: una petición por
modelo en la parte 2, y otra en la 3 (dos si responde 503, que `HFClient`
reintenta). El token no se imprime, y lo que devuelve el proveedor pasa por
`_tapar` por si llevara algo con forma de token.

Ejecutar desde la raíz: .venv/bin/python spikes/hf_credito.py
"""

import asyncio
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.config.settings import settings  # noqa: E402
from backend.core.idioma import INGLES  # noqa: E402
from backend.integrations.nlp.model_cards import model_id_de  # noqa: E402
from backend.integrations.nlp.remote import HFClient  # noqa: E402

URL_CUENTA = "https://huggingface.co/api/whoami-v2"
TITULAR = "You Won't Believe What Happened Next"
# Las mismas preguntas con que E3-02 y #109 midieron a BART.
ETIQUETAS = ["clickbait", "factual news"]
# BART no tiene ficha: es el zero-shot que se configura con #159.
ZERO_SHOT = "facebook/bart-large-mnli"


def _tapar(texto: str) -> str:
    """Tapa cualquier cosa con forma de token de Hugging Face."""
    return re.sub(r"hf_[A-Za-z0-9]{6,}", "hf_***", texto)


def _cuenta(cliente: httpx.Client, cabeceras: dict[str, str]) -> None:
    respuesta = cliente.get(URL_CUENTA, headers=cabeceras)
    print(f"1 · cuenta (whoami-v2): HTTP {respuesta.status_code}")
    if respuesta.status_code != 200:
        return
    datos = respuesta.json()
    papel = ((datos.get("auth") or {}).get("accessToken") or {}).get("role")
    print(
        f"    tipo {datos.get('type')} · isPro {datos.get('isPro')} · "
        f"canPay {datos.get('canPay')} · papel del token {papel}"
    )


def _codigos(cliente: httpx.Client, cabeceras: dict[str, str]) -> None:
    print("2 · hf-inference, directo:")
    pruebas = [
        ("tono", model_id_de("analyze_sentiment", INGLES), {"inputs": TITULAR}),
        (
            "zero-shot",
            ZERO_SHOT,
            {"inputs": TITULAR, "parameters": {"candidate_labels": ETIQUETAS}},
        ),
        ("dedicada", model_id_de("detect_clickbait", INGLES), {"inputs": TITULAR}),
    ]
    for nombre, modelo, cuerpo in pruebas:
        respuesta = cliente.post(
            f"{HFClient.BASE_URL}{modelo}", headers=cabeceras, json=cuerpo
        )
        principio = _tapar(respuesta.text[:160].replace("\n", " "))
        print(f"    {nombre:<9} {modelo}: HTTP {respuesta.status_code} · {principio}")


async def _produccion() -> None:
    print("3 · lo que devuelve HFClient (la tarjeta, con nlp_backend=remote):")
    cliente = HFClient()
    tono = await cliente.classify(TITULAR, model_id_de("analyze_sentiment", INGLES))
    bart = await cliente.zero_shot(TITULAR, ZERO_SHOT, ETIQUETAS)
    for nombre, resultado in [("tono", tono), ("zero-shot", bart)]:
        dicho = resultado.data if resultado.success else resultado.error
        print(f"    {nombre:<9} {_tapar(str(dicho))}")


def main() -> None:
    # `base_api` registra el cuerpo de cada error, y ya sale en la parte 2.
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL)
    )
    token = settings.hf_token.get_secret_value()
    print(f"fecha: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · httpx {httpx.__version__}")
    print(f"token en el .env: {'sí' if token else 'no'}")
    cabeceras = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30) as cliente:
        _cuenta(cliente, cabeceras)
        _codigos(cliente, cabeceras)
    asyncio.run(_produccion())


if __name__ == "__main__":
    main()
