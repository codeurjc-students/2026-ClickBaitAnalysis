"""Fichas de modelos (R3.9): divulgación de los modelos/señales del sistema.

Fuente única, consultable en runtime vía la tool ``describe_models`` y
forward-compatible con un futuro frontend. El campo ``type`` enlaza con R3.8:
marca qué señales son white-box (``interpretable``) frente a caja negra
(``opaco``), pasando por las ``híbrido`` (decisión transparente, feature opaca).

La otra mitad de R3.9 (intercambiar modelos por configuración) la cubre la
factoría ``get_nlp_backend`` vía el setting ``nlp_backend`` (remote/local).

El campo ``signal`` es la **clave de máquina**: debe coincidir EXACTAMENTE con el
nombre de la tool MCP que produce esa señal, porque ``/analyze`` lo usa para
buscar la ficha de cada resultado. No es una etiqueta legible —para eso están
``name`` y ``task``— y meterle anotaciones («detect_clickbait (zero-shot)»)
rompe la búsqueda en silencio: no lanza excepción, simplemente no encuentra la
ficha. ``test_model_cards_signals_match_registered_tools`` lo vigila.

El campo ``dimension`` indica QUÉ mide cada señal, no cómo de transparente es:

- ``forma``  — sensacionalismo en la redacción del titular (estilo).
- ``engano`` — que el titular prometa algo que el cuerpo no cumple.
- ``tono``   — carga emocional del texto; no es una señal de clickbait.

Es lo que permite a ``/analyze`` agrupar los veredictos por dimensión en vez de
promediar señales que miden cosas distintas: tres señales de *forma* de acuerdo
no significan que el titular engañe. Sin este campo, el backend tendría que
cablear qué señal es cuál — justo lo que se evita.
"""


def cards_by_signal() -> dict[str, dict]:
    """Índice de fichas por nombre de tool.

    Vive aquí y no en quien lo usa porque lo necesitan DOS consumidores —la
    orquestación de ``/analyze``, para leer la dimensión de cada señal, y el
    catálogo, para adjuntar la ficha— y dos copias del mismo índice acabarían
    divergiendo.
    """
    return {card["signal"]: card for card in MODEL_CARDS}


MODEL_CARDS = [
    {
        "signal": "detect_clickbait",
        "name": "facebook/bart-large-mnli",
        "task": "Clasifica el titular como clickbait vs factual por inferencia natural (NLI, zero-shot).",
        "type": "opaco",
        "dimension": "forma",
        "limitations": [
            "Modelo genérico de NLI, no entrenado específicamente en clickbait.",
            "Caja negra: sin explicación intrínseca (post-hoc opcional, R3.11).",
            "Solo inglés.",
            "En backend remoto (HF): sujeto a timeouts/caídas del proveedor.",
        ],
        "backend": "remote | local",
    },
    {
        "signal": "analyze_sentiment",
        "name": "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "task": "Análisis de sentimiento en 3 clases (positivo / neutral / negativo).",
        "type": "opaco",
        "dimension": "tono",
        "limitations": [
            "Entrenado en tuits, no en titulares de noticias.",
            "Caja negra.",
            "Solo inglés.",
        ],
        "backend": "remote | local",
    },
    {
        "signal": "detect_clickbait_incoherence",
        "dimension": "engano",
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "task": "Similitud coseno titular↔contenido; una similitud baja indica posible clickbait por incoherencia.",
        "type": "híbrido",
        "limitations": [
            "Decisión transparente (umbral sobre la similitud) pero feature opaca (embeddings).",
            "Umbral (0.3) sin calibrar.",
            "Necesita el cuerpo/teaser, no solo el titular.",
            "Solo inglés.",
        ],
        "backend": "local",
    },
    {
        "signal": "detect_clickbait_lexical",
        "dimension": "forma",
        "name": "Léxico por reglas (listas de cues de Chakraborty et al. 2016)",
        "task": "Detecta pistas léxicas/estructurales de clickbait y devuelve qué cues dispararon y dónde.",
        "type": "interpretable",
        "limitations": [
            "Capta clickbait de forma/estilo, no de engaño semántico.",
            "THRESHOLD=1 agresivo (un solo cue ya lo marca).",
            "Superficial: no entiende el significado.",
            "No generaliza fuera de dominio sin adaptación — medido: F1 0.843 en titulares de noticias (Chakraborty test) vs 0.498 en tuits (Webis-17).",
            "Solo inglés.",
        ],
        "backend": "local",
    },
    {
        "signal": "detect_clickbait_linear",
        "dimension": "forma",
        "name": "Regresión logística sobre features léxicas (entrenada en Chakraborty)",
        "task": "Clickbait ponderado: aprende el peso de cada pista y devuelve los cues que más contribuyeron al veredicto.",
        "type": "interpretable",
        "limitations": [
            "Detecta clickbait de ESTILO: entrenado con etiquetas por-fuente (Chakraborty) → puede señalar estilo editorial más que engaño (sesgo de fuente / shortcut learning).",
            "NO generaliza fuera de dominio sin adaptación — medido: F1 0.865 en titulares de noticias (Chakraborty test) vs 0.476 en tuits (Webis-17).",
            "No capta engaño semántico (usa las mismas pistas de superficie que el léxico).",
            "Solo inglés.",
        ],
        "backend": "local",
    },
]
