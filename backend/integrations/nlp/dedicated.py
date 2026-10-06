"""Señal de clickbait con un modelo dedicado (issue #115).

Las otras señales de titular ya tenían módulo propio —``lexical``, ``linear``,
``incoherence``—; ésta no, y llamaba al backend directamente desde las DOS
fachadas. Esa asimetría es la causa de que su id y sus etiquetas acabaran
duplicados (#116): no había dónde ponerlos. Aquí los hay.

POR QUÉ ESTE MODELO

``Stremie/roberta-base-clickbait`` sustituye a ``facebook/bart-large-mnli``, que
se eligió en E3-02 **por eliminación** —era lo único que el serverless de
HuggingFace servía para esto— y nunca por medida. Medido en #109, aquél acertaba
el 63,7 %: la señal más floja de la dimensión.

Lo que distingue a éste no es su puntuación, es **de qué aprendió**. Se entrenó
sobre Webis-Clickbait-17, cuyas etiquetas son el juicio de anotadores humanos, no
la fuente que publicó el titular. Es la única señal del sistema con supervisión
no sesgada por fuente, y eso importa más que unos puntos de acierto: el sesgo de
fuente es el fallo que #76 destapó y que #109 cuantificó.

Su patrón es además **el inverso** del que descartó a ``elozano``:

    elozano   99,7 % en Chakraborty (su corpus)  ->  F1 0,185 en Webis
    Stremie    0,631 F1 en Webis (su corpus)     ->  F1 0,946 en Chakraborty

Alto FUERA y más bajo DENTRO. Eso es generalizar, no memorizar — y su 0,946 en
Chakraborty supera al 0,865 que el lineal saca *dentro* de su propio dominio.

Con él, la dimensión ``form`` deja el 15 % de titulares sin resolver en vez del
37 %, y sólo el 20 % de esa ambigüedad restante es error suyo (antes, el 78 %).
Por eso **vuelve a votar**: el motivo por el que #109 lo silenció desaparece.

Lo que NO arregla: sigue siendo opaca, y su independencia del par acoplado es
**desconocida** —no buena—, porque su único corpus de test honesto es el fácil.
Ver la ficha.

DESDE #159, OTRO MODELO SE PUEDE LLAMAR DE OTRA FORMA

Por configuración, la señal puede ejecutar un clasificador con otro vocabulario
o un modelo zero-shot, que no se entrenó para la tarea y elige entre las
etiquetas que se le preguntan. Lo que no cambia es la salida: las etiquetas del
contrato, traducidas igual en los dos caminos.
"""

from collections.abc import Mapping

from backend.core.models import ToolResult
from backend.integrations.nlp.model_cards import model_id_de

MODEL = model_id_de("detect_clickbait")

CLASIFICACION = "text-classification"
ZERO_SHOT = "zero-shot-classification"

# El vocabulario del modelo NO sale hacia fuera. La tool MCP publica
# `clickbait`/`factual news`, que es contrato leído por el LLM (spike #82), y
# mantenerlo estable significa que el próximo cambio de modelo no se propaga a
# quien consume la señal. Traducir aquí es lo que convierte las etiquetas del
# modelo en un detalle de implementación.
ETIQUETAS = {
    "Clickbait": "clickbait",
    "Not Clickbait": "factual news",
}

# Lo que se le pregunta a un zero-shot si la configuración no dice otra cosa:
# las etiquetas del contrato tal cual, las mismas con que E3-02 y #109 midieron
# a `facebook/bart-large-mnli`.
ETIQUETAS_ZERO_SHOT = {
    "clickbait": "clickbait",
    "factual news": "factual news",
}


async def detect(
    api,
    headline: str,
    model: str | None = None,
    task: str = CLASIFICACION,
    etiquetas: Mapping[str, str] | None = None,
) -> ToolResult:
    """Clasifica un titular con el modelo de la señal y normaliza su etiqueta.

    Recibe el backend en vez de construirlo: las dos fachadas ya tienen uno
    —cacheado, porque cargar el modelo cuesta— y crear otro aquí tiraría esa
    caché y duplicaría el modelo en memoria.

    Y desde #119 recibe también el **id del modelo**, por el mismo motivo un
    nivel más abajo: resolverlo aquí obligaría a este módulo a leer `settings`,
    y entonces no se podría importar sin un `.env` con las claves de API. Desde
    #159, igual el modo (`task`) y las `etiquetas`: qué palabra del modelo
    corresponde a cada etiqueta del contrato. En un zero-shot, esas palabras son
    las que se le preguntan. Los defectos son los de la ficha, así que quien no
    configure nada no nota nada.
    """
    if not headline or not headline.strip():
        return ToolResult.fail("El titular está vacío o no es válido")

    modelo = model or MODEL
    if task == ZERO_SHOT:
        traduccion = etiquetas or ETIQUETAS_ZERO_SHOT
        respuesta = await api.zero_shot(headline, modelo, list(traduccion))
    else:
        traduccion = etiquetas or ETIQUETAS
        respuesta = await api.classify(headline, modelo)
    if not respuesta.has_content():
        return respuesta

    cruda = respuesta.data["label"]
    if cruda not in traduccion:
        # Falla en vez de dejar pasar la etiqueta cruda. Si se colara, el
        # extractor de veredicto la compararía con «clickbait», no coincidiría,
        # y TODOS los titulares saldrían factuales — un fallo total que no
        # levanta ninguna excepción y que sólo se ve midiendo.
        #
        # Las dos causas medidas (`spikes/invocacion_casos.py`): un clasificador
        # con otro vocabulario («Normal» en vez de «Not Clickbait», #119) y un
        # modelo de inferencia llamado como clasificador («neutral»).
        return ToolResult.fail(
            f"{modelo} devolvió la etiqueta «{cruda}», que no está en el mapeo "
            f"{sorted(traduccion)}: revisa qué etiquetas usa el modelo (`labels`), "
            "o si es de inferencia (NLI) y hay que llamarlo como zero-shot (`task`)"
        )

    return ToolResult.ok({**respuesta.data, "label": traduccion[cruda]})
