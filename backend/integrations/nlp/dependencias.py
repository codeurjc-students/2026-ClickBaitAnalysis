"""Si una dependencia pesada está instalada, y qué decir cuando no lo está.

**Por qué existe.** Dos de las cinco señales sólo funcionan con paquetes que
`requirements.txt` NO trae: la dedicada necesita `torch` y la incoherencia
`sentence-transformers`. No es un descuido — es la decisión que mantiene ligero
al CI, que mockea los backends y nunca ejecuta un modelo. Instalarlos es trabajo
de la imagen de despliegue.

La consecuencia es que **el estado «falta la dependencia» es normal**, no
excepcional, y por eso merece un mensaje propio en vez de caer en el `except`
genérico de cada señal. Medido el 2026-09-08 sobre una instalación con
`requirements.txt` a secas, esto es lo que decía antes:

- dedicada → ``Error inesperado usando el modelo Stremie/…: name 'torch' is not
  defined``. Un `NameError`, no un `ImportError`: `transformers` avisa por
  consola de que no encuentra PyTorch y después revienta con una variable sin
  definir. Quien lo lee en la pantalla piensa que hay un bug en este código.
- incoherencia → ``Error inesperado calculando incoherencia: No module named
  'sentence_transformers'``. Más claro, pero sigue diciendo *inesperado* de algo
  que se espera, y no dice qué hacer.

**Se pregunta, no se importa.** `find_spec` resuelve el módulo sin ejecutarlo,
así que esto NO deshace los imports perezosos de `local.py` e `incoherence.py`
— que son justo lo que permite que el CI corra sin torch.

**Lo mismo con los modelos (#162).** La imagen de despliegue trae horneados los
modelos de las fichas y corre con `HF_HUB_OFFLINE=1`, así que uno puesto por
`NLP_MODELS` no puede descargarse. Otra vez un estado normal, y otra vez salía
como ``Error inesperado usando el modelo …: We couldn't connect to
'https://huggingface.co'…``. Aquí no se puede preguntar antes sin copiar qué
ficheros necesita cada librería, así que se interpreta el fallo — y medido el
2026-09-17, no todo `OSError` es este caso:

- sin red y nunca horneado → `OSError` causado por `LocalEntryNotFoundError`, igual
  en `transformers` y en `sentence-transformers`. **Éste es el caso.**
- sin red y horneado a medias → `ValueError` en el clasificador, `OSError` sin
  causa en la incoherencia. Una imagen mal construida: sí es una avería.
- con red y un id que no existe → `OSError` causado por `RepositoryNotFoundError`.
"""

from importlib.util import find_spec

from huggingface_hub import is_offline_mode
from huggingface_hub.errors import LocalEntryNotFoundError

from backend.integrations.nlp.model_cards import MODEL_CARDS


class FaltaDependencia(RuntimeError):
    """Lo que necesita esta señal —un paquete o un modelo— no está en esta instalación.

    Excepción propia y no un `RuntimeError` pelado porque quien la captura tiene
    que distinguirla de un fallo de verdad: su mensaje ya está redactado para
    quien mira la pantalla, así que se devuelve tal cual en vez de envolverlo en
    «Error inesperado …».
    """


# Cómo se instala cada una. La rueda de torch se pide del índice de CPU a
# propósito: son 769 MB frente a 1,2 GB de la variante CUDA, y la máquina de
# despliegue no tiene GPU. Medido el 2026-09-08, junto con lo demás: con esta
# rueda el arranque en frío baja de 52,4 s a 24,2 s y la RAM de 1.645 a 1.201 MB.
COMANDOS = {
    "torch": "pip install torch --index-url https://download.pytorch.org/whl/cpu",
    "sentence_transformers": "pip install sentence-transformers",
}


def motivo_si_falta(paquete: str) -> str | None:
    """El motivo que enseñar si `paquete` no está instalado; `None` si lo está.

    Devuelve el mensaje COMPLETO, no un fragmento, porque quien llama lo usa
    para saltarse su propio «Error inesperado»: el prefijo es la mitad de lo que
    hacía inútil al mensaje viejo.

    El nombre del paquete se escribe con guiones —como se instala— y no con el
    guion bajo del import, que es lo que se teclea en el `pip install` y lo que
    aparece en `requirements.txt`.
    """
    if find_spec(paquete) is not None:
        return None

    instalable = paquete.replace("_", "-")
    comando = COMANDOS.get(paquete, f"pip install {instalable}")

    return (
        f"Esta señal necesita `{instalable}`, y esta instalación no lo trae. "
        "No es una avería: `requirements.txt` no lo incluye a propósito —pesa "
        "cientos de MB y las pruebas lo mockean—, así que lo instala la imagen "
        f"de despliegue. Para habilitarla aquí: {comando}"
    )


def motivo_si_falta_modelo(modelo: str, error: BaseException) -> str | None:
    """El motivo que enseñar si `error` es no poder descargar `modelo`; `None` si no.

    Se le pasa el error que lanzó la librería al cargar. Las tres condiciones son
    necesarias, y cada una evita un mensaje falso:

    1. **La causa es `LocalEntryNotFoundError`**: «no está en la caché y no pude
       preguntar al Hub». Sin esto, un id mal escrito o un horneado a medias
       recibirían este mensaje.
    2. **La descarga está desactivada.** Esa misma causa aparece si se cae la red
       sin la bandera puesta, y entonces decir que está desactivada sería falso.
    3. **El modelo no es de los declarados.** Uno declarado tenía que venir
       horneado: si falta, la imagen está mal construida, y eso SÍ es una avería
       que debe seguir diciéndose como tal.
    """
    if not isinstance(error.__cause__, LocalEntryNotFoundError):
        return None
    # `is_offline_mode` lee la variable de entorno UNA vez, al importar
    # `huggingface_hub`, así que las pruebas sustituyen esta función en vez de
    # tocar el entorno.
    if not is_offline_mode():
        return None
    if modelo in {ficha["model_id"] for ficha in MODEL_CARDS}:
        return None

    return (
        f"El modelo `{modelo}` no está descargado en esta instalación y la "
        "descarga está desactivada (`HF_HUB_OFFLINE=1`). No es una avería: la "
        "imagen de despliegue trae horneados sólo los modelos que declaran las "
        "fichas, y éste llega por configuración (`NLP_MODELS`). Para probarlo "
        "aquí, arrancar con `HF_HUB_OFFLINE=0` y se descargará al usarse."
    )
