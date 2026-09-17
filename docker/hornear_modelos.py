"""Descarga, al construir la imagen, los modelos que declaran las fichas.

Se descarga por FORMATO DE FICHERO, sin decir qué librería carga cada modelo.
Decirlo aquí sería una segunda copia de un dato que ya vive en `incoherence.py`
y en `local.py`: la misma divergencia de siempre.

Qué se descarga, y por qué (medido el 2026-09-16):

- Sólo la rama `main`. Los dos RoBERTa tienen ahí únicamente
  `pytorch_model.bin`; su `model.safetensors` vive en una PR de conversión
  automática del Hub. Cargar el modelo con red descarga los dos (~2 GB), pero
  SIN red `transformers` sólo ve `main`: sin el `.bin` la carga falla, sin el
  `safetensors` funciona. En una imagen que corre sin red, el de la PR sería
  ~1 GB de peso muerto.
- De pesos, `model.safetensors` si está en `main` y si no `pytorch_model.bin`:
  el mismo orden en que los busca `transformers`.
- Configuración y vocabulario: `*.json` y `*.txt`.

Comprobado sin red, cargando los tres modelos como la aplicación: 1,1 GB.
"""

from huggingface_hub import HfApi, snapshot_download

from backend.integrations.nlp.model_cards import MODEL_CARDS

api = HfApi()

for ficha in MODEL_CARDS:
    identificador = ficha["model_id"]
    if identificador is None:
        continue  # léxico y lineal: código propio, no un modelo descargable

    ficheros = api.list_repo_files(identificador)
    pesos = (
        "model.safetensors" if "model.safetensors" in ficheros else "pytorch_model.bin"
    )
    # Lista los nombres de `main`, se queda con los que encajan en los patrones
    # y descarga sólo ésos: lo que no encaja nunca se transfiere.
    snapshot_download(identificador, allow_patterns=["*.json", "*.txt", pesos])
    print(f"horneado: {ficha['signal']} -> {identificador} ({pesos})")
