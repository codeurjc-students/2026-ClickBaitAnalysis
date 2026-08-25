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
            "NO VOTA (#109): se muestra pero su veredicto no entra en la dimensión `forma`. Es la señal más floja en los dos dominios medidos — 63.7% de acierto en Chakraborty dev (vs 87.0% del léxico y 89.3% del lineal) y F1 0.405 en Webis-17 (vs 0.526 y 0.519) — y al discrepar en solitario dejaba el 37% de los titulares en AMBIGUO.",
            "PLACEHOLDER pendiente de #115: elegido en E3-02 por eliminación (lo único que el serverless de HuggingFace servía entonces), no por medida. Se conserva visible en vez de retirarlo porque, al no haber visto ningún corpus de clickbait, es la única señal inmune al sesgo de fuente (#78).",
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
            "THRESHOLD=1 agresivo: el veredicto es EXACTAMENTE el indicador «¿disparó algún cue?» — verificado, coincide con `any(featurize_cues(h))` en el 100% de 6400 titulares de dev. El score pesa en la explicación, no en la decisión.",
            "Superficial: no entiende el significado.",
            "No generaliza fuera de dominio sin adaptación — medido: F1 0.843 en titulares de noticias (Chakraborty test) vs 0.498 en tuits (Webis-17).",
            "Techo de recall por cobertura del léxico: el 15.5% de los positivos de Chakraborty dev y el 32.5% de los de Webis-17 no disparan ningún cue, así que son indetectables por construcción (techo 84.5% y 67.5%). Ampliar los rasgos es #75.",
            "A favor, y medido: su recall sigue el juicio humano de intensidad casi linealmente en Webis-17 (51.6% / 75.8% / 85.5% por tercios de `truthMean`, n=62 por tramo). Es la señal que mejor generaliza fuera de dominio de las cuatro evaluadas, por delante incluso del lineal, que se estanca en los tramos altos (61.3% -> 62.9%).",
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
            "ACOPLADA al léxico POR CONSTRUCCIÓN, no por correlación: `featurize_cues()` llama a `lexical.detect()`, así que el veredicto del léxico es una función determinista de su propio input. kappa 0.880 en Chakraborty dev, pero la mitad de ese acuerdo es punto ciego compartido — en el 50% de los titulares el vector sale vacío y ambas responden «no» sin mirar (acuerdo forzado del 100%). Donde el vector tiene contenido el acuerdo baja al 88.0%, y al 59.1% en Webis-17.",
            "Techo de recall heredado del featurizado: 84.5% en Chakraborty y 67.5% en Webis-17, con un recall medido de 0.478. Reentrenar los pesos no puede superarlo, porque w·0 = 0 sea cual sea w — de ahí que #75 (featurización) sea prerrequisito de #78 (reentrenamiento).",
            "Solo inglés.",
        ],
        "backend": "local",
    },
]
