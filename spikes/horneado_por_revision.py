"""#234 (2026-10-09) - ¿Carga sin red el commit fijado de cada modelo horneado?

`docker/hornear_modelos.py` descarga el commit que fija cada ficha. Pero
descargar un commit no escribe `refs/main`, y sin red los modelos se piden por
su nombre, que la caché resuelve leyendo ese fichero. Esto lo comprueba sin
construir la imagen y sin bajar pesos, sobre una copia de la caché de
desarrollo:

1. copia los modelos de las fichas a una caché temporal, con enlaces duros (ni
   ocupa espacio ni toca la original), y les borra `refs/main`;
2. sin red, los carga por el mismo camino que producción: deberían fallar;
3. hornea en la copia con la función de `hornear_modelos.py`, que sólo pide
   metadatos al Hub: los pesos ya están;
4. sin red otra vez: deberían cargar, y responder a un titular.

Cada carga va en un proceso aparte, porque `HF_HUB_OFFLINE` se lee al
importar `huggingface_hub`.

Ejecutar desde la raíz:

    .venv/bin/python spikes/horneado_por_revision.py
"""

import asyncio
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

COPIA = Path("/tmp/hf_revision")
TITULARES = {
    "en": "You Won't Believe What This Dog Did Next",
    "es": "No vas a creer lo que hizo este perro",
}
CUERPO = "A small study in mice found modest effects of the diet after eight weeks."


def _con_modelo() -> list[dict]:
    from backend.integrations.nlp.model_cards import MODEL_CARDS

    return [dict(ficha) for ficha in MODEL_CARDS if ficha["model_id"] is not None]


def _en_otro_proceso(fase: str, sin_red: bool) -> None:
    """Una fase en un proceso nuevo, con la caché temporal y, si toca, sin red."""
    entorno = {
        **os.environ,
        "HF_HOME": str(COPIA),
        "HF_HUB_CACHE": str(COPIA / "hub"),
        "NLP_BACKEND": "local",
    }
    entorno.pop("HF_HUB_OFFLINE", None)
    if sin_red:
        entorno["HF_HUB_OFFLINE"] = "1"
    subprocess.run([sys.executable, __file__, fase], cwd=RAIZ, env=entorno, check=False)


def copiar() -> None:
    from huggingface_hub import constants

    origen = Path(constants.HF_HUB_CACHE)
    shutil.rmtree(COPIA, ignore_errors=True)
    (COPIA / "hub").mkdir(parents=True)
    for ficha in _con_modelo():
        carpeta = "models--" + ficha["model_id"].replace("/", "--")
        destino = COPIA / "hub" / carpeta
        shutil.copytree(origen / carpeta, destino, symlinks=True, copy_function=os.link)
        # Borrar el enlace de la copia no toca el de la caché original.
        (destino / "refs" / "main").unlink()
        instantaneas = sorted(
            ruta.name[:12] for ruta in (destino / "snapshots").iterdir()
        )
        print(f"  {ficha['model_id']}: sin refs/main · instantáneas {instantaneas}")


async def cargar() -> None:
    from backend.integrations.nlp.factory import (
        get_incoherence_detector,
        get_model_id,
        get_nlp_backend,
    )

    for ficha in _con_modelo():
        idioma, titular = ficha["language"], TITULARES[ficha["language"]]
        if ficha["signal"] == "detect_clickbait_incoherence":
            resultado = await get_incoherence_detector(idioma).detect(titular, CUERPO)
        else:
            modelo = get_model_id(ficha["signal"], idioma)
            resultado = await get_nlp_backend().classify(titular, modelo)
        if not resultado.has_content():
            print(
                f"  FALLA  {ficha['model_id']} ({idioma}): {(resultado.error or '')[:160]}"
            )
            continue
        datos = resultado.unwrap()
        if "similarity" in datos:
            respuesta = f"similitud {datos['similarity']:.3f}"
        else:
            respuesta = f"{datos['label']} {datos['score']:.3f}"
        print(f"  CARGA  {ficha['model_id']} ({idioma}): {respuesta}")


def hornear() -> None:
    from huggingface_hub import HfApi

    especificacion = importlib.util.spec_from_file_location(
        "hornear_modelos", RAIZ / "docker" / "hornear_modelos.py"
    )
    assert especificacion is not None and especificacion.loader is not None
    hornear_modelos = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(hornear_modelos)

    api = HfApi()
    for ficha in _con_modelo():
        pesos = hornear_modelos.hornear(ficha["model_id"], ficha["revision"], api)
        referencia = (
            COPIA
            / "hub"
            / ("models--" + ficha["model_id"].replace("/", "--"))
            / "refs"
            / "main"
        )
        print(
            f"  {ficha['model_id']}: {pesos} · refs/main {referencia.read_text()[:12]}"
        )


if __name__ == "__main__":
    # Los encabezados, antes que la salida de cada proceso hijo, también por
    # una tubería.
    sys.stdout.reconfigure(line_buffering=True)  # pyright: ignore[reportAttributeAccessIssue]
    fase = sys.argv[1] if len(sys.argv) > 1 else None
    if fase == "cargar":
        asyncio.run(cargar())
    elif fase == "hornear":
        hornear()
    else:
        print("== 1 · la copia, sin refs/main")
        copiar()
        print("\n== 2 · sin red y sin refs/main: deberían fallar")
        _en_otro_proceso("cargar", sin_red=True)
        print("\n== 3 · horneado en la copia")
        _en_otro_proceso("hornear", sin_red=False)
        print("\n== 4 · sin red, después de hornear: deberían cargar")
        _en_otro_proceso("cargar", sin_red=True)
