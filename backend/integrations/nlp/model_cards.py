"""Fichas de modelos (R3.9): divulgación de los modelos/señales del sistema.

Fuente única, consultable en runtime vía la tool ``describe_models`` y
forward-compatible con un futuro frontend. El campo ``type`` enlaza con R3.8:
marca qué señales son white-box (``interpretable``) frente a caja negra
(``opaque``), pasando por las ``hybrid`` (decisión transparente, feature opaca).

CUIDADO CON LA OTRA MITAD DE R3.9

Este docstring afirmaba que «intercambiar modelos por configuración» lo cubría la
factoría ``get_nlp_backend`` vía el setting ``nlp_backend``. **Es falso, y se
comprobó al cambiar de modelo en #115**: ``nlp_backend`` decide DÓNDE corre el
modelo (remoto o local), no CUÁL es. Sustituir el modelo de la señal de clickbait
exigió tocar esta tabla, escribir ``dedicated.py`` y añadir un mapeo de
etiquetas — todo código, que es justo lo que el requisito excluye.

Queda por tanto **sin cumplir**, y anotado como tal en vez de darlo por hecho.
#116 lo dejó a un paso —el id ya vive en un único sitio, así que leerlo de
settings con la ficha como defecto es pequeño—, pero hay una tensión de fondo: el
mapeo de etiquetas NO se configura igual de fácil, porque cada modelo trae su
propio vocabulario. Intercambiar cualquier modelo por configuración sólo es
realista dentro de una familia que comparta convención.

TRES CAMPOS QUE PARECEN LO MISMO Y NO LO SON

- ``signal`` — **clave de máquina**: coincide EXACTAMENTE con el nombre de la
  tool MCP que produce esa señal, porque ``/analyze`` la usa para buscar la ficha
  de cada resultado. Meterle anotaciones («detect_clickbait (zero-shot)») rompe
  la búsqueda en silencio: no lanza excepción, simplemente no encuentra la ficha.
  ``test_model_cards_signals_match_registered_tools`` lo vigila.
- ``model_id`` — **identificador en HuggingFace**, y la fuente ÚNICA desde la que
  el orquestador y la tool construyen su llamada. Es ``None`` en las señales que
  no son un modelo descargable (léxico y lineal), y ese ``None`` es información.
- ``name`` — **etiqueta para personas**, la que se pinta en la interfaz.

Estaban fundidos en ``name``, que era un id crudo en tres fichas y prosa en dos,
así que el id acabó cableado en cinco sitios y las dos fachadas —REST y MCP—
podían quedarse con modelos distintos sin que nada fallara (#116). Separarlos es
lo que permite que el id viva en un solo lugar; ``test_los_ids_de_las_fichas_son_los_que_se_usan``
comprueba que la llamada real usa el de la ficha, que es lo único que impide que
vuelvan a separarse.

El campo ``dimension`` indica QUÉ mide cada señal, no cómo de transparente es:

- ``form``      — sensacionalismo en la redacción del titular (estilo).
- ``deception`` — que el titular prometa algo que el cuerpo no cumple.
- ``tone``      — carga emocional del texto; no es una señal de clickbait.

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
        "model_id": "Stremie/roberta-base-clickbait",
        "name": "RoBERTa dedicado (entrenado en Webis-17)",
        "task": "Clasifica el titular como clickbait vs factual con un modelo afinado específicamente para esta tarea.",
        "type": "opaque",
        "dimension": "form",
        "limitations": [
            "Caja negra: sin explicación intrínseca (post-hoc opcional, R3.11).",
            "Solo inglés. Entrenado sobre `postText` de Webis-17, es decir TUITS de medios, no titulares de portada.",
            "INDEPENDENCIA DESCONOCIDA, que no es lo mismo que buena: en Chakraborty coincide mucho con el par acoplado (kappa 0.726 con el léxico y 0.772 con el lineal), pero ahí tres clasificadores competentes coinciden por fuerza, así que ese número no informa. Medirla bien exige un corpus con etiqueta humana que el modelo no haya visto — candidato en #121: Webis-Clickbait-16.",
            "SPLIT DE ENTRENAMIENTO DESCONOCIDO: su ficha dice «Webis-Clickbait-17» sin precisar cuál de los dos splits, que son disjuntos. Medido en ambos: F1 0.631 en `train170331` (2459) y 0.758 en `validation170630` (19484). Ninguno de los dos se parece a la puntuación de un modelo evaluado sobre su propio entrenamiento, así que NO se afirma contaminación — pero tampoco se descarta que viera uno de ellos.",
            "Sustituye a `facebook/bart-large-mnli` (#115), elegido en E3-02 por eliminación y medido en #109 al 63.7%. La sustitución sí se decidió por medida: F1 0.946 en Chakraborty — corpus que NO vio — frente al 0.473 del anterior, y con la ambigüedad de `forma` cayendo del 37% al 15%.",
            "A favor, y es lo que más pesa: entrenado con ETIQUETA HUMANA (`truthMean` de anotadores), no por fuente. Es la única señal del sistema con supervisión no sesgada por el medio que publicó el titular — el fallo que #76 destapó y #109 cuantificó.",
            "No memoriza, verificado: rinde MEJOR fuera de su dominio (F1 0.946 en Chakraborty) que dentro (0.631 y 0.758 en los dos splits de Webis), el patrón inverso al de `elozano/bert-base-cased-clickbait-news`, descartado por 99.7% dentro y F1 0.185 fuera.",
            "Ese 0.946 de Chakraborty NO significa que sea mejor ahí (#121): Chakraborty etiqueta por fuente y ese método no puede producir casos dudosos, así que mide sólo la mitad fácil del problema. Restringiendo Webis a los titulares donde los 5 anotadores coinciden — lo más parecido a Chakraborty que hay dentro de Webis — sube a F1 0.906, y el resto lo explica el balance de clases.",
            "Contexto imprescindible para leer cualquiera de estos números: el techo humano de la tarea es F1 0.665, y sólo el 34.9% de los titulares tiene a los 5 anotadores de acuerdo (#121). Sus errores se concentran donde las personas discrepan (92.9% de los fallos en el 65.1% dudoso) y su confianza baja ahí (0.918 vs 0.834), sin haber visto nunca los juicios individuales.",
        ],
        "backend": "remote | local",
    },
    {
        "signal": "analyze_sentiment",
        "model_id": "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "name": "RoBERTa afinado en tuits (3 clases)",
        "task": "Análisis de sentimiento en 3 clases (positivo / neutral / negativo).",
        "type": "opaque",
        "dimension": "tone",
        "limitations": [
            "Entrenado en tuits, no en titulares de noticias.",
            "Caja negra.",
            "Solo inglés.",
        ],
        "backend": "remote | local",
    },
    {
        "signal": "detect_clickbait_incoherence",
        "dimension": "deception",
        "model_id": "sentence-transformers/all-MiniLM-L6-v2",
        "name": "MiniLM-L6-v2 (embeddings de frase)",
        "task": "Similitud coseno titular↔contenido; una similitud baja indica posible clickbait por incoherencia.",
        "type": "hybrid",
        "limitations": [
            "Decisión transparente (umbral sobre la similitud) pero feature opaca (embeddings).",
            "Umbral 0.3 CALIBRADO en #92 sobre 19484 pares de Webis-17, eligiéndolo en una mitad y midiéndolo en la otra: es el punto de mayor precisión de la curva (0.649 en test) a cambio de pronunciarse sólo en el 7.4% de los titulares. ROC-AUC de la señal 0.720.",
            "Sólo lee los primeros 1000 caracteres del cuerpo, porque el modelo trunca a 256 tokens de todas formas. Medido: trocear el artículo entero y quedarse con la mayor similitud da AUC 0.717 frente a 0.716 truncando — el resto del texto no aportaba nada.",
            "REDUNDANTE con la señal dedicada: `dedicada ∨ incoherencia` BAJA la precisión de 0.709 a 0.673, así que los casos que añade son mayoritariamente falsos. Aporta en cambio a las señales débiles (`linear ∨ incoherencia` sube F1 de 0.448 a 0.517).",
            "Precisión de sólo 0.12 en el subconjunto donde ninguna señal de forma dispara — que es justamente el hueco que esta dimensión existe para cubrir (titulares sobrios que engañan: 470 de 8793). No es culpa del umbral: con un 5.3% de positivos y AUC 0.628 ahí, la precisión alta es inalcanzable.",
            "Necesita el cuerpo/teaser, no solo el titular.",
            "Solo inglés. Calibrado sobre TUITS con su artículo enlazado, no sobre titulares de portada.",
        ],
        "backend": "local",
    },
    {
        "signal": "detect_clickbait_lexical",
        "dimension": "form",
        # Sin `model_id`: no hay nada que descargar. Son regex y listas de cues.
        "model_id": None,
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
        "dimension": "form",
        # Sin `model_id`: los pesos son un JSON del repo, no un modelo de la Hub.
        "model_id": None,
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
