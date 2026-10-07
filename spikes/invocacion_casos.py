"""#159 (2026-10-06) - Qué pasa al llamar a un modelo con un modo que no es el suyo.

`detect_clickbait` va a poder configurarse con un clasificador o con un
zero-shot, y la combinación puede no encajar: un clasificador pedido como
zero-shot, o un modelo de inferencia (NLI) pedido como clasificador. Antes de
escribir ningún mensaje de error se provocan los casos, como en #158 y #162, y
se mira qué devuelve de verdad cada uno.

Por cada modelo y modo, con el `LocalNLPClient` de producción, sobre un titular
clickbait y uno factual:

- las etiquetas del modelo (`label2id` de su configuración) y, en zero-shot,
  el `entailment_id` que calcula `transformers` (-1 si no encuentra una
  etiqueta que empiece por «entail»);
- lo que devuelve el pipeline, con todas las puntuaciones;
- lo que `transformers` escribe en su log mientras tanto.

Con `--remoto`, además, el zero-shot por la Inference API de Hugging Face
(`HFClient`): si sigue sirviendo BART, que en E3-02 era lo único que servía para
esta tarea. Lee el token del `.env` y no lo imprime.

Con `--analisis`, en vez de todo lo anterior, la comprobación de #159 ya
implementado: cada configuración de `NLP_MODELS` por `analyze()`, el camino de
producción, con los dos titulares. Un titular solo no basta: con `elozano`, el
clickbait salía bien y el factual fallaba (#119).

Ejecutar desde la raíz:
    .venv/bin/python spikes/invocacion_casos.py [--remoto]
    .venv/bin/python spikes/invocacion_casos.py --analisis
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.integrations.nlp.local import LocalNLPClient  # noqa: E402

CLASIFICACION = "text-classification"
ZERO_SHOT = "zero-shot-classification"
ETIQUETAS_ZERO_SHOT = ["clickbait", "factual news"]

TITULARES = {
    "clickbait": "10 Amazing Things You Won't Believe",
    "factual": "Federal Reserve raises interest rates by a quarter point",
}

CASOS = [
    ("Stremie/roberta-base-clickbait", CLASIFICACION, "el de hoy"),
    (
        "elozano/bert-base-cased-clickbait-news",
        CLASIFICACION,
        "otro vocabulario (#119)",
    ),
    ("facebook/bart-large-mnli", ZERO_SHOT, "el de antes de #115"),
    ("MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli", ZERO_SHOT, "otro NLI"),
    ("Stremie/roberta-base-clickbait", ZERO_SHOT, "clasificador pedido como zero-shot"),
    ("facebook/bart-large-mnli", CLASIFICACION, "NLI pedido como clasificador"),
]


class Recogedor(logging.Handler):
    """Guarda lo que `transformers` escribe en su log."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.mensajes: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.mensajes.append(record.getMessage())


def local() -> None:
    recogedor = Recogedor()
    logging.getLogger("transformers").addHandler(recogedor)
    cliente = LocalNLPClient()

    for modelo, tarea, nota in CASOS:
        print(f"\n== {modelo} como {tarea} ({nota})")
        recogedor.mensajes.clear()
        pipe = cliente._get_pipeline(tarea, modelo)
        print(f"   etiquetas del modelo: {pipe.model.config.label2id}")
        if tarea == ZERO_SHOT:
            print(f"   entailment_id: {pipe.entailment_id}")
        for clase, titular in TITULARES.items():
            if tarea == ZERO_SHOT:
                salida = pipe(titular, candidate_labels=ETIQUETAS_ZERO_SHOT)
                puntos = ", ".join(
                    f"{etiqueta} {puntuacion:.3f}"
                    for etiqueta, puntuacion in zip(
                        salida["labels"], salida["scores"], strict=True
                    )
                )
            else:
                salida = pipe(titular, top_k=None)
                puntos = ", ".join(
                    f"{prediccion['label']} {prediccion['score']:.3f}"
                    for prediccion in salida
                )
            print(f"   {clase:9s} -> {puntos}")
        for mensaje in recogedor.mensajes:
            print(f"   log de transformers: {mensaje}")


async def remoto() -> None:
    from backend.integrations.nlp.remote import HFClient

    cliente = HFClient()
    for modelo in ("facebook/bart-large-mnli", "Stremie/roberta-base-clickbait"):
        print(f"\n== remoto: {modelo} como {ZERO_SHOT}")
        for clase, titular in TITULARES.items():
            resultado = await cliente.zero_shot(titular, modelo, ETIQUETAS_ZERO_SHOT)
            print(
                f"   {clase:9s} -> "
                + (
                    str(resultado.data)
                    if resultado.success
                    else f"FALLO: {resultado.error}"
                )
            )


# Lo que se configura en `NLP_MODELS["detect_clickbait"]` para cada prueba de
# `--analisis`. `None` es sin configurar: el dedicado de la ficha.
BART = "facebook/bart-large-mnli"
DEBERTA = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
ELOZANO = "elozano/bert-base-cased-clickbait-news"
CONFIGURACIONES = [
    ("sin configurar", None),
    ("BART como zero-shot", {"id": BART, "task": ZERO_SHOT}),
    ("DeBERTa como zero-shot", {"id": DEBERTA, "task": ZERO_SHOT}),
    (
        "BART con otra pregunta",
        {
            "id": BART,
            "task": ZERO_SHOT,
            "labels": {
                "sensationalist headline": "clickbait",
                "news report": "factual news",
            },
        },
    ),
    (
        "elozano con sus etiquetas",
        {"id": ELOZANO, "labels": {"Clickbait": "clickbait", "Normal": "factual news"}},
    ),
    ("elozano sin ellas (#119)", ELOZANO),
    (
        "el dedicado como zero-shot",
        {"id": "Stremie/roberta-base-clickbait", "task": ZERO_SHOT},
    ),
    ("BART como clasificador", BART),
]


async def analisis() -> None:
    """Cada configuración por `analyze()`, el camino de producción, en local.

    La configuración se valida como al arrancar (`Settings`), y se pone en el
    `settings` del proceso, que es lo que leen la factoría y el orquestador.
    """
    from backend.analysis.domain import AnalyzeRequest
    from backend.analysis.orchestrator import analyze
    from backend.config.settings import Settings, settings

    settings.nlp_backend = "local"
    for nombre, configuracion in CONFIGURACIONES:
        modelos = {} if configuracion is None else {"detect_clickbait": configuracion}
        # Validado como lo validaría el arranque, con las claves de mentira.
        settings.nlp_models = Settings(
            nlp_models=modelos, guardian_api_key="x", nyt_api_key="x", hf_token="x"
        ).nlp_models
        print(f"\n== {nombre}")
        for clase, titular in TITULARES.items():
            respuesta = await analyze(AnalyzeRequest(headline=titular))
            senal = next(
                resultado_de_senal
                for resultado_de_senal in respuesta.signals
                if resultado_de_senal.name == "detect_clickbait"
            )
            if senal.status.value == "ok" and senal.data:
                resultado = f"{senal.data['label']} {senal.data['score']:.3f}"
            else:
                resultado = f"{senal.status.value}: {senal.detail}"
            print(f"   {clase:9s} -> {resultado}")
        print(f"   rótulo de la tarjeta: {senal.label}")


if __name__ == "__main__":
    if "--analisis" in sys.argv:
        asyncio.run(analisis())
    else:
        local()
        if "--remoto" in sys.argv:
            asyncio.run(remoto())
