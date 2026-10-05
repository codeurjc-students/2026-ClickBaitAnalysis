# factory.py
"""Qué hay configurado de verdad: qué backend, qué modelo y qué ficha.

Este módulo es —con `remote.py`, que necesita el token— **el único de la capa NLP
al que se le permite leer `settings`**, y `tests/test_arquitectura.py` lo vigila.
Esa restricción es la que decide la forma de todo lo de abajo: los detectores no
resuelven su configuración, la **reciben**. Si `incoherence.py` llamara aquí para
saber su id, arrastraría `settings` —cuyos campos de API son obligatorios— y
dejaría de poder importarse sin un `.env`, que es justo lo que el test protege.

Su oficio era «decidir DÓNDE corre el modelo». Desde #119 decide también **cuál
es** y **qué ficha se publica**, que es el mismo trabajo con un parámetro más; y
desde #93, **con qué umbral decide** cada señal que corta por uno.
"""

from functools import lru_cache

from backend.config.settings import UmbralConfigurable, settings
from backend.integrations.nlp import lexical, linear
from backend.integrations.nlp.base import NLPBackend
from backend.integrations.nlp.incoherence import IncoherenceDetector
from backend.integrations.nlp.local import LocalNLPClient  # local.py
from backend.integrations.nlp.model_cards import (
    FichaDeclarada,
    cards_by_signal,
    model_id_de,
)
from backend.integrations.nlp.outputs import FichaModelo
from backend.integrations.nlp.remote import HFClient  # remote.py

# Los umbrales POR DEFECTO, leídos del detector que los usa (#93). Viven allí y
# no aquí porque allí está escrito por qué valen lo que valen (E4-03, #92); aquí
# sólo se decide si la configuración los sustituye.
_UMBRALES_DEL_DETECTOR: dict[UmbralConfigurable, float] = {
    "detect_clickbait_lexical": lexical.THRESHOLD,
    "detect_clickbait_incoherence": IncoherenceDetector.THRESHOLD,
}


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
def _detector_para(model_id: str, threshold: float) -> IncoherenceDetector:
    """Un detector por modelo Y umbral: la caché va por el valor de la
    configuración (#119), así que cambiar cualquiera de los dos da otro.

    Cambiar sólo el umbral carga el modelo otra vez en la instancia nueva. Se
    acepta: el umbral no se mueve con el sistema en marcha, se pone al
    desplegar o para un experimento (#93).
    """
    return IncoherenceDetector(model_id, threshold)


def get_incoherence_detector() -> IncoherenceDetector:
    """El detector de incoherencia configurado, siempre el mismo objeto.

    Vive aquí y no en cada fachada por el mismo motivo que el backend: carga su
    modelo de forma perezosa y lo cachea **por instancia**, así que dos
    instancias serían dos copias del modelo en memoria. Con un único punto,
    `precalentar()` calienta exactamente el objeto que va a usar la petición —
    que antes era una advertencia escrita en el orquestador y ahora lo garantiza
    la construcción.
    """
    return _detector_para(
        get_model_id("detect_clickbait_incoherence"),
        get_threshold("detect_clickbait_incoherence"),
    )


def get_threshold(signal: UmbralConfigurable) -> float:
    """El umbral con el que decide una señal: el configurado, o el de su detector.

    Como el modelo, se resuelve en cada llamada: una constante de módulo
    quedaría fijada en el primer import, y cambiar la configuración después
    sería un ajuste que no hace nada sin fallar (#87).
    """
    return settings.nlp_thresholds.get(signal, _UMBRALES_DEL_DETECTOR[signal])


def get_top_cues() -> int:
    """Cuántas pistas devuelve el lineal como explicación: las configuradas, o
    las de su detector. No toca el veredicto: la probabilidad suma todas."""
    return settings.nlp_linear_top_cues or linear.TOP_CUES


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

    Y en las dos ramas, **las notas de operación no salen** (#211): son de quien
    opera el sistema, no de quien lee la señal. Por aquí pasan
    ``describe_models``, el catálogo y el orquestador, así que ésta es la única
    puerta entre la ficha declarada y la publicada.

    Desde #93, un umbral puesto por configuración añade un aviso delante: ver
    ``_con_aviso_de_umbral``.
    """
    ficha = cards_by_signal()[signal]
    configurado = settings.nlp_models.get(signal)

    if not configurado or configurado == ficha["model_id"]:
        return _con_aviso_de_umbral(signal, _publicable(ficha))

    return _con_aviso_de_umbral(
        signal,
        {
            **_publicable(ficha),
            "model_id": configurado,
            "name": f"{configurado} (puesto por configuración)",
            "limitations": [
                f"SIN EVALUAR EN ESTE PROYECTO. Este modelo se ha puesto por configuración en lugar de `{ficha['model_id']}`, así que las limitaciones medidas de aquél no se publican aquí: eran suyas. Lo que sigue siendo cierto es lo que describe la señal y no al modelo — mide `{ficha['dimension']}` y es de tipo `{ficha['type']}`.",
            ],
        },
    )


def _con_aviso_de_umbral(signal: str, ficha: FichaModelo) -> FichaModelo:
    """La ficha, con un aviso delante si el umbral no es el de sus medidas (#93).

    Al revés que con otro modelo (#119), las limitaciones NO se quitan: el
    modelo es el mismo, y límites como «sólo inglés» o «acoplada al léxico»
    siguen siendo ciertos. Lo que deja de valer son las cifras de acierto,
    medidas con el umbral por defecto, y eso es lo que dice el aviso.
    """
    if signal not in _UMBRALES_DEL_DETECTOR:
        return ficha
    defecto = _UMBRALES_DEL_DETECTOR[signal]
    umbral = get_threshold(signal)
    if umbral == defecto:
        return ficha
    aviso = (
        f"UMBRAL PUESTO POR CONFIGURACIÓN: {umbral:g} en lugar de {defecto:g}. "
        f"Las cifras de esta ficha se midieron con {defecto:g}; con este umbral, "
        "la precisión y el recall son otros, sin medir en este proyecto."
    )
    return {**ficha, "limitations": [aviso, *ficha["limitations"]]}


def _publicable(ficha: FichaDeclarada) -> FichaModelo:
    """La ficha sin las notas de operación (#211).

    Clave a clave y no copiando el diccionario: así no se cuela nada que se
    declare de más, y si ``FichaModelo`` gana un campo, pyright exige
    añadirlo aquí.
    """
    return {
        "signal": ficha["signal"],
        "model_id": ficha["model_id"],
        "name": ficha["name"],
        "task": ficha["task"],
        "type": ficha["type"],
        "dimension": ficha["dimension"],
        "limitations": ficha["limitations"],
        "backend": ficha["backend"],
    }
