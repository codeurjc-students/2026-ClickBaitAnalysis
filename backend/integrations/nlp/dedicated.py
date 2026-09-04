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
"""

from backend.core.models import ToolResult
from backend.integrations.nlp.model_cards import cards_by_signal

MODEL = cards_by_signal()["detect_clickbait"]["model_id"]

# El vocabulario del modelo NO sale hacia fuera. La tool MCP publica
# `clickbait`/`factual news`, que es contrato leído por el LLM (spike #82), y
# mantenerlo estable significa que el próximo cambio de modelo no se propaga a
# quien consume la señal. Traducir aquí es lo que convierte las etiquetas del
# modelo en un detalle de implementación.
ETIQUETAS = {
    "Clickbait": "clickbait",
    "Not Clickbait": "factual news",
}


async def detect(api, headline: str) -> ToolResult:
    """Clasifica un titular con el modelo dedicado y normaliza su etiqueta.

    Recibe el backend en vez de construirlo: las dos fachadas ya tienen uno
    —cacheado, porque cargar el modelo cuesta— y crear otro aquí tiraría esa
    caché y duplicaría el modelo en memoria.
    """
    if not headline or not headline.strip():
        return ToolResult.fail("El titular está vacío o no es válido")

    respuesta = await api.classify(headline, MODEL)
    if not respuesta.has_content():
        return respuesta

    cruda = respuesta.data["label"]
    if cruda not in ETIQUETAS:
        # Falla en vez de dejar pasar la etiqueta cruda. Si se colara, el
        # extractor de veredicto la compararía con «clickbait», no coincidiría,
        # y TODOS los titulares saldrían factuales — un fallo total que no
        # levanta ninguna excepción y que sólo se ve midiendo.
        return ToolResult.fail(
            f"{MODEL} devolvió la etiqueta «{cruda}», que no está en el mapeo "
            f"{sorted(ETIQUETAS)}: revisa si el modelo ha cambiado de convención"
        )

    return ToolResult.ok({**respuesta.data, "label": ETIQUETAS[cruda]})
