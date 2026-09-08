# factory.py
"""Qué hay configurado de verdad: qué backend, qué modelo y qué ficha.

Este módulo es —con `client.py`, que necesita el token— **el único de la capa NLP
al que se le permite leer `settings`**, y `tests/test_arquitectura.py` lo vigila.
Esa restricción es la que decide la forma de todo lo de abajo: los detectores no
resuelven su configuración, la **reciben**. Si `incoherence.py` llamara aquí para
saber su id, arrastraría `settings` —cuyos campos de API son obligatorios— y
dejaría de poder importarse sin un `.env`, que es justo lo que el test protege.

Su oficio era «decidir DÓNDE corre el modelo». Desde #119 decide también **cuál
es** y **qué ficha se publica**, que es el mismo trabajo con un parámetro más.
"""

from functools import lru_cache

from backend.config.settings import settings
from backend.integrations.nlp.base import NLPBackend
from backend.integrations.nlp.client import HFClient  # client.py
from backend.integrations.nlp.incoherence import IncoherenceDetector
from backend.integrations.nlp.local import LocalNLPClient  # local.py
from backend.integrations.nlp.model_cards import cards_by_signal, model_id_de
from backend.integrations.nlp.outputs import FichaModelo


@lru_cache(maxsize=2)
def _backend_para(nombre: str) -> NLPBackend:
    """Un cliente por backend, construido la primera vez que hace falta.

    **La clave de caché es la configuración**, y eso resuelve #87 sin inventar
    nada: antes el cliente se creaba a nivel de módulo, así que quedaba atado al
    backend que dijera `settings` en el instante de importar y cambiarlo después
    no tenía efecto. Ahora un cambio de setting produce otra clave, y el cliente
    correcto sale solo.

    Se reutiliza la instancia a propósito: `LocalNLPClient` cachea los pipelines
    y crear uno por petición recargaría el modelo cada vez. Lo que estaba mal era
    **cuándo** se creaba, no que se reutilizara.

    `maxsize=2` porque los backends son dos. Volver al anterior no recarga nada,
    a cambio de tenerlos los dos residentes — que es lo que se quiere en una
    prueba y es inocuo en despliegue, donde sólo se usa uno.
    """
    match nombre:
        case "local":
            return LocalNLPClient()
        case "remote":
            return HFClient()
        case _:
            return LocalNLPClient()  # Default


def get_nlp_backend() -> NLPBackend:
    """El backend NLP que dice la configuración AHORA."""
    return _backend_para(settings.nlp_backend)


@lru_cache(maxsize=2)
def _detector_para(model_id: str) -> IncoherenceDetector:
    return IncoherenceDetector(model_id)


def get_incoherence_detector() -> IncoherenceDetector:
    """El detector de incoherencia configurado, siempre el mismo objeto.

    Vive aquí y no en cada fachada por el mismo motivo que el backend: carga su
    modelo de forma perezosa y lo cachea **por instancia**, así que dos
    instancias serían dos copias del modelo en memoria. Con un único punto,
    `precalentar()` calienta exactamente el objeto que va a usar la petición —
    que antes era una advertencia escrita en el orquestador y ahora lo garantiza
    la construcción.
    """
    return _detector_para(get_model_id("detect_clickbait_incoherence"))


def get_model_id(signal: str) -> str:
    """El modelo que ejecuta una señal: el configurado, o el de su ficha.

    Se resuelve en cada llamada y no al importar. Parece un detalle y no lo es:
    hasta #119 esto vivía en constantes de módulo —`MODEL` en `dedicated.py`,
    `_SENTIMENT_MODEL` en el orquestador— así que el valor quedaba fijado en el
    primer import y ninguna configuración posterior lo movía.
    """
    return settings.nlp_models.get(signal) or model_id_de(signal)


def ficha_efectiva(signal: str) -> FichaModelo:
    """La ficha que se publica, con el modelo que se ejecuta de verdad.

    Cuando el modelo está sobrescrito por configuración pasan dos cosas, y las
    dos importan:

    1. **El `model_id` publicado es el efectivo.** Si no, se reabre el fallo que
       #116 vino a cerrar: dos cadenas para el mismo modelo, una divulgada y otra
       ejecutada, divergiendo sin que nada falle.
    2. **Las limitaciones medidas NO se publican.** Son de otro modelo: se
       midieron sobre él, issue a issue (#109, #115, #121). Heredarlas sería
       divulgar como propias unas medidas ajenas, que es peor que no tener
       ninguna — y la ausencia es información: dice que eso es un experimento,
       no una señal caracterizada.

    Lo que SÍ sobrevive es lo que describe **el hueco** y no a su ocupante: qué
    dimensión mide, de qué tipo es y qué tarea cumple. Por eso se conserva el
    resto de la ficha en vez de devolverla vacía.
    """
    ficha = cards_by_signal()[signal]
    configurado = settings.nlp_models.get(signal)

    if not configurado or configurado == ficha["model_id"]:
        return ficha

    return {
        **ficha,
        "model_id": configurado,
        "name": f"{configurado} (puesto por configuración)",
        "limitations": [
            f"SIN EVALUAR EN ESTE PROYECTO. Este modelo se ha puesto por configuración en lugar de `{ficha['model_id']}`, así que las limitaciones medidas de aquél no se publican aquí: eran suyas. Lo que sigue siendo cierto es lo que describe la señal y no al modelo — mide `{ficha['dimension']}` y es de tipo `{ficha['type']}`.",
        ],
    }
