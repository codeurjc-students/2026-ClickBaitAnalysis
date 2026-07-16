"""Fichas de modelos (R3.9): divulgación de los modelos/señales del sistema.

Fuente única, consultable en runtime vía la tool ``describe_models`` y
forward-compatible con un futuro frontend. El campo ``type`` enlaza con R3.8:
marca qué señales son white-box (``interpretable``) frente a caja negra
(``opaco``), pasando por las ``híbrido`` (decisión transparente, feature opaca).

La otra mitad de R3.9 (intercambiar modelos por configuración) la cubre la
factoría ``get_nlp_backend`` vía el setting ``nlp_backend`` (remote/local).
"""

MODEL_CARDS = [
    {
        "signal": "detect_clickbait (zero-shot)",
        "name": "facebook/bart-large-mnli",
        "task": "Clasifica el titular como clickbait vs factual por inferencia natural (NLI, zero-shot).",
        "type": "opaco",
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
        "limitations": [
            "Entrenado en tuits, no en titulares de noticias.",
            "Caja negra.",
            "Solo inglés.",
        ],
        "backend": "remote | local",
    },
    {
        "signal": "detect_clickbait_incoherence",
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
        "name": "Léxico por reglas (listas de cues de Chakraborty et al. 2016)",
        "task": "Detecta pistas léxicas/estructurales de clickbait y devuelve qué cues dispararon y dónde.",
        "type": "interpretable",
        "limitations": [
            "Capta clickbait de forma/estilo, no de engaño semántico.",
            "THRESHOLD=1 agresivo (un solo cue ya lo marca).",
            "Superficial: no entiende el significado.",
            "Solo inglés.",
        ],
        "backend": "local",
    },
    {
        "signal": "detect_clickbait_linear",
        "name": "Regresión logística sobre features léxicas (entrenada en Chakraborty)",
        "task": "Clickbait ponderado: aprende el peso de cada pista y devuelve los cues que más contribuyeron al veredicto.",
        "type": "interpretable",
        "limitations": [
            "Entrenado en titulares de noticias en inglés (Chakraborty); los pesos por-cue pueden no generalizar a otros dominios.",
            "No capta engaño semántico (usa las mismas pistas de superficie que el léxico).",
            "Solo inglés.",
        ],
        "backend": "local",
    },
]
