# factory.py
"""Qué hay configurado de verdad: qué backend, qué modelo y qué ficha.

Este módulo es —con `remote.py`, que necesita el token— **el único de la capa NLP
al que se le permite leer `settings`**, y `tests/test_arquitectura.py` lo vigila.
Esa restricción es la que decide la forma de todo lo de abajo: los detectores no
resuelven su configuración, la **reciben**. Si `incoherence.py` llamara aquí para
saber su id, arrastraría `settings` —cuyos campos de API son obligatorios— y
dejaría de poder importarse sin un `.env`, que es justo lo que el test protege.

Su oficio era «decidir DÓNDE corre el modelo». Desde #119 decide también **cuál
es** y **qué ficha se publica**, que es el mismo trabajo con un parámetro más;
desde #93, **con qué umbral decide** cada señal que corta por uno; desde #159,
**cómo se le llama** al modelo de `detect_clickbait` (`get_invocacion`); y desde
#229, **en qué idiomas se analiza** (`motivo_si_no_se_analiza`).
"""

from functools import lru_cache

from backend.config.settings import (
    ModeloConInvocacion,
    UmbralConfigurable,
    settings,
)
from backend.core.idioma import INGLES, NOMBRES, Idioma
from backend.integrations.nlp import dedicated, lexical, linear
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

# En qué idiomas se analiza un titular (#229). Por ahora, sólo inglés: las cinco
# señales se entrenaron o se midieron en inglés. Desde #230 lo decidirá cada
# señal según tenga modelo en ese idioma.
_IDIOMAS_ANALIZADOS: frozenset[Idioma] = frozenset({INGLES})


def motivo_si_no_se_analiza(idioma: Idioma) -> str | None:
    """Por qué no se analiza un titular en ese idioma, o `None` si se analiza.

    La frase vive aquí, y no en cada fachada, para que el análisis completo y las
    herramientas sueltas digan exactamente lo mismo (la lección de #116: dos
    copias de un texto acaban diciendo cosas distintas).
    """
    if idioma in _IDIOMAS_ANALIZADOS:
        return None
    return (
        f"El titular parece estar en {NOMBRES[idioma]}: por ahora las señales "
        "sólo analizan titulares en inglés."
    )


def motivo_si_el_cuerpo_no_se_compara(idioma: Idioma) -> str | None:
    """Por qué la incoherencia no compara un cuerpo en ese idioma, o `None` si
    lo compara.

    La puerta del titular no basta: la incoherencia compara titular y cuerpo
    con un modelo inglés, y con el cuerpo en español la similitud se hunde
    aunque diga lo mismo, hasta cruzar el umbral (medido en #229). Las demás
    señales no leen el cuerpo, así que se siguen ejecutando.
    """
    if idioma in _IDIOMAS_ANALIZADOS:
        return None
    return (
        f"El cuerpo parece estar en {NOMBRES[idioma]}: por ahora la incoherencia "
        "sólo compara titular y cuerpo en inglés."
    )


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
    return get_invocacion(signal).id


def get_invocacion(signal: str) -> ModeloConInvocacion:
    """El modelo de una señal y cómo se le llama (#159): el configurado, o el de
    su ficha como clasificador con sus etiquetas de siempre.

    Una cadena en `nlp_models` es sólo el id, como desde #119; el objeto, en
    `detect_clickbait`, trae además el modo y las etiquetas.
    """
    configurado = settings.nlp_models.get(signal)
    if isinstance(configurado, ModeloConInvocacion):
        return configurado
    return ModeloConInvocacion(id=configurado or model_id_de(signal))


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
    ``_con_aviso_de_umbral``. Y desde #159 cuenta también CÓMO se llama al
    modelo: un zero-shot o un clasificador con otras etiquetas es otra señal
    aunque el id sea el mismo, y la ficha publica qué se le pregunta.
    """
    ficha = cards_by_signal()[signal]
    configurado = settings.nlp_models.get(signal)
    if isinstance(configurado, ModeloConInvocacion):
        invocacion, modelo = configurado, configurado.id
    else:
        invocacion, modelo = None, configurado

    if not modelo or (modelo == ficha["model_id"] and _como_se_midio(invocacion)):
        return _con_aviso_de_umbral(signal, _publicable(ficha))

    sustitucion = (
        f"Este modelo se ha puesto por configuración en lugar de `{ficha['model_id']}`, así que las limitaciones medidas de aquél no se publican aquí: eran suyas."
        if modelo != ficha["model_id"]
        else "Este modelo se llama por configuración de otra forma que como se midió, así que sus limitaciones medidas no se publican aquí: eran de la otra forma."
    )
    zero_shot = invocacion is not None and invocacion.task == dedicated.ZERO_SHOT
    publicada: FichaModelo = {
        **_publicable(ficha),
        "model_id": modelo,
        "name": f"{modelo} ({'zero-shot, ' if zero_shot else ''}puesto por configuración)",
        "limitations": [
            f"SIN EVALUAR EN ESTE PROYECTO. {sustitucion} Lo que sigue siendo cierto es lo que describe la señal y no al modelo — mide `{ficha['dimension']}` y es de tipo `{ficha['type']}`.",
            *_como_se_le_llama(invocacion),
        ],
    }
    if zero_shot:
        publicada["task"] = (
            "Clasifica el titular como clickbait vs factual con un modelo zero-shot: "
            "no se entrenó para esta tarea, y elige entre las etiquetas que se le "
            "preguntan."
        )
    return _con_aviso_de_umbral(signal, publicada)


def _como_se_midio(invocacion: ModeloConInvocacion | None) -> bool:
    """¿Se llama al modelo como se midió: clasificador, con sus etiquetas?"""
    return invocacion is None or (
        invocacion.task == dedicated.CLASIFICACION
        and invocacion.labels in (None, dedicated.ETIQUETAS)
    )


def _como_se_le_llama(invocacion: ModeloConInvocacion | None) -> list[str]:
    """Lo que la ficha tiene que decir del modo y de las etiquetas (#159)."""
    if invocacion is None:
        return []
    if invocacion.task == dedicated.ZERO_SHOT:
        preguntas = invocacion.labels or dedicated.ETIQUETAS_ZERO_SHOT
        lista = " y ".join(
            f"«{pregunta}» (→ {etiqueta})" for pregunta, etiqueta in preguntas.items()
        )
        return [
            f"ZERO-SHOT: no se entrenó para esta tarea; se le pregunta entre {lista}. La redacción de esas etiquetas forma parte de la pregunta: con otras, el mismo modelo da otro resultado."
        ]
    if invocacion.labels:
        traduccion = ", ".join(
            f"«{palabra}» → {etiqueta}"
            for palabra, etiqueta in invocacion.labels.items()
        )
        return [f"Sus etiquetas se traducen así: {traduccion}."]
    return []


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
