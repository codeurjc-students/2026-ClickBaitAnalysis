"""Descarga, al construir la imagen, los modelos que declaran las fichas.

Se descarga por FORMATO DE FICHERO, sin decir qué librería carga cada modelo.
Decirlo aquí sería una segunda copia de un dato que ya vive en `incoherence.py`
y en `local.py`: la misma divergencia de siempre.

Qué se descarga, y por qué (medido el 2026-09-16):

- Sólo la rama `main`, y desde #234 sólo el commit que fija la ficha. Los dos
  RoBERTa tienen ahí únicamente `pytorch_model.bin`; su `model.safetensors`
  vive en una PR de conversión automática del Hub. Cargar el modelo con red
  descarga los dos (~2 GB), pero SIN red `transformers` sólo ve `main`: sin el
  `.bin` la carga falla, sin el `safetensors` funciona. En una imagen que corre
  sin red, el de la PR sería ~1 GB de peso muerto.
- De pesos, `model.safetensors` si está en ese commit y si no
  `pytorch_model.bin`: el mismo orden en que los busca `transformers`.
- Configuración y vocabulario: `*.json` y `*.txt`.

Comprobado sin red, cargando los tres modelos como la aplicación: 1,1 GB.

LA REVISIÓN FIJADA (#234)

Cada ficha con modelo trae `revision`, el commit de los pesos que se midieron,
y se descarga ése, no lo que haya en `main` el día del build. Pero descargar un
commit no basta: sin red, `transformers` y `sentence-transformers` piden el
modelo por su nombre, y la caché resuelve el nombre leyendo `refs/main`, un
fichero con el commit al que apunta `main`. `snapshot_download` sólo lo
escribe cuando se le pide una rama, no un commit
(`_cache_commit_hash_for_specific_revision`, en `huggingface_hub` 1.16.1): la
imagen se construiría bien y los modelos fallarían al cargar. Por eso se
escribe aquí, apuntando al commit fijado, y se comprueba que la caché lo
resuelve así antes de dar el modelo por horneado.
"""

import sys
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download, try_to_load_from_cache

from backend.integrations.nlp.model_cards import MODEL_CARDS


def hornear(identificador: str, revision: str, api: HfApi) -> str:
    """Descarga el commit fijado y apunta `main` a él. Devuelve los pesos elegidos."""
    ficheros = api.list_repo_files(identificador, revision=revision)
    pesos = (
        "model.safetensors" if "model.safetensors" in ficheros else "pytorch_model.bin"
    )
    # Lista los nombres de ese commit, se queda con los que encajan en los
    # patrones y descarga sólo ésos: lo que no encaja nunca se transfiere.
    instantanea = Path(
        snapshot_download(
            identificador, revision=revision, allow_patterns=["*.json", "*.txt", pesos]
        )
    )
    # La instantánea es `<modelo>/snapshots/<commit>`, y `refs/`, de `<modelo>`.
    referencia = instantanea.parent.parent / "refs" / "main"
    referencia.parent.mkdir(parents=True, exist_ok=True)
    referencia.write_text(revision)

    # Lo mismo que hará la carga sin red: pedir un fichero por el nombre.
    resuelto = try_to_load_from_cache(identificador, "config.json")
    if not isinstance(resuelto, str) or Path(resuelto).parent.name != revision:
        sys.exit(
            f"{identificador}: sin red, la caché no lo resuelve al commit "
            f"{revision} sino a {resuelto}."
        )
    return pesos


if __name__ == "__main__":
    api = HfApi()
    for ficha in MODEL_CARDS:
        identificador, revision = ficha["model_id"], ficha["revision"]
        if identificador is None:
            continue  # léxico y lineal: código propio, no un modelo descargable
        if revision is None:
            sys.exit(
                f"{identificador} no fija su revisión en la ficha: un modelo sin "
                "fijar no se hornea (#234)."
            )
        pesos = hornear(identificador, revision, api)
        print(
            f"horneado: {ficha['signal']} ({ficha['language']}) -> "
            f"{identificador} @ {revision[:12]} ({pesos})"
        )
