"""Revisión de antes de congelar (2026-11-21) - Los textos de más de 512 piezas.

La pipeline de text-classification de `transformers` no recorta por defecto, y
`LocalNLPClient.classify` le pasaba el texto tal cual: con uno más largo que las
posiciones del modelo, la dedicada y el tono fallaban dentro de torch y salían
en `error` con «motivo no previsto». Desde la revisión, `classify` pasa
`truncation=True, max_length=MAX_PIEZAS`. Este guion lo mide con los cuatro
modelos que pasan por `classify` (la dedicada y el tono, en inglés y en
español), los de las fichas, en CPU y sin red, como en la imagen:

- un texto largo tal cual (lo que hacía `classify`), sólo con `truncation=True`
  y como lo llama hoy;
- el tope que declara el tokenizador de cada modelo (`model_max_length`): si es
  absurdo, `truncation=True` solo no recorta nada;
- `classify` con el texto largo, el camino servido;
- y que con un titular normal recortar no cambia la salida.

Ejecutar desde la raíz:

    .venv/bin/python spikes/recorte_512.py

Resultados (2026-11-21, `3aea084` con el recorte de `classify`, torch
2.12.1+cu130 con la GPU oculta y transformers 5.12.0, en el PC):

| Modelo | Tope | Piezas | Tal cual | `truncation` | Y `max_length` |
|---|---|---|---|---|---|
| `Stremie/roberta-base-clickbait` | 512 | 643 | falla | Clickbait 0,880 | Clickbait 0,880 |
| `cardiffnlp/twitter-roberta-base-sentiment-latest` | 1e+30 | 643 | falla | falla | negative 0,770 |
| `ggcastle/beto-clickbait-es` | 512 | 722 | falla | Clickbait 0,617 | Clickbait 0,617 |
| `lxyuan/distilbert-base-multilingual-cased-sentiments-student` | 512 | 802 | falla | neutral 0,582 | neutral 0,582 |

Los dos RoBERTa fallan con `index 514 is out of bounds for dimension 1 with
size 514`, y BETO y DistilBERT con `The size of tensor a (…) must match the
size of tensor b (512)`. `classify` responde con los cuatro, y un titular
normal sale idéntico recortado o no.
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import structlog

# Antes de importar nada de `backend`: torch y `huggingface_hub` las leen al
# importarse. Son las condiciones de `ejemplos_formulario.py` (#282).
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.core.idioma import ESPANOL, INGLES  # noqa: E402
from backend.integrations.nlp.factory import get_model_id  # noqa: E402
from backend.integrations.nlp.local import MAX_PIEZAS, LocalNLPClient  # noqa: E402
from spikes.ejemplos_formulario import ajustes_puestos  # noqa: E402

# Sin los avisos del registro: lo que interesa de `classify` sale en su resultado.
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))

TAREA = "text-classification"
SENALES = ("detect_clickbait", "analyze_sentiment")
# Unos 3.000 caracteres, como las entradillas más largas de NewsData (3.271).
LARGOS = {
    INGLES: "You won't believe what happened next. " * 80,
    ESPANOL: "No vas a creer lo que pasó después. " * 80,
}
CORTOS = {
    INGLES: "You Won't Believe What This Dog Did Next",
    ESPANOL: "No vas a creer lo que hizo este perro",
}


def _intento(pipe, texto: str, **opciones) -> str:
    """La etiqueta y la puntuación, o el fallo, tal como salen de la pipeline."""
    try:
        salida = pipe(texto, **opciones)[0]
    except Exception as error:
        return f"falla: {type(error).__name__}: {str(error)[:80]}"
    return f"{salida['label']} {salida['score']:.3f}"


def condiciones() -> str:
    """Con qué se mide; se para si no es lo que se sirve."""
    import torch
    import transformers

    if torch.cuda.is_available():
        raise SystemExit("torch ve una GPU: la medida tiene que ser en CPU")
    if puestos := ajustes_puestos():
        raise SystemExit(f"ajustes que apartan la medida de las fichas: {puestos}")
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    cambios = subprocess.run(
        ["git", "status", "--short", "--", "backend"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return (
        f"== {commit}{' con cambios en backend/' if cambios else ''}, torch "
        f"{torch.__version__}, transformers {transformers.__version__}, en CPU "
        f"y sin red; MAX_PIEZAS {MAX_PIEZAS}"
    )


async def main() -> None:
    cliente = LocalNLPClient()
    for idioma in (INGLES, ESPANOL):
        largo, corto = LARGOS[idioma], CORTOS[idioma]
        for senal in SENALES:
            modelo = get_model_id(senal, idioma)
            pipe = cliente._get_pipeline(TAREA, modelo)
            piezas = len(pipe.tokenizer(largo)["input_ids"])
            servido = await cliente.classify(largo, modelo)
            igual = pipe(corto) == pipe(corto, truncation=True, max_length=MAX_PIEZAS)
            print(f"\n-- {senal} ({idioma}): {modelo}")
            print(
                f"   tope del tokenizador {pipe.tokenizer.model_max_length:g}; "
                f"el texto largo, {len(largo)} caracteres y {piezas} piezas"
            )
            print(f"   tal cual:          {_intento(pipe, largo)}")
            print(f"   truncation=True:   {_intento(pipe, largo, truncation=True)}")
            print(
                "   y max_length:      "
                f"{_intento(pipe, largo, truncation=True, max_length=MAX_PIEZAS)}"
            )
            print(
                "   classify:          "
                + ("ok" if servido.success else f"falla: {servido.error}")
            )
            print(f"   un titular, igual recortado: {igual}")


if __name__ == "__main__":
    print(condiciones())
    asyncio.run(main())
