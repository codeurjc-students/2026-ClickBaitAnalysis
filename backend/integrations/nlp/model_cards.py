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

LA REVISIÓN DE LOS PESOS (#234)

``revision`` es el commit del Hub de los pesos que se midieron, entero.
``docker/hornear_modelos.py`` descarga justo ése, no lo que haya en ``main``
el día en que se construye la imagen: si el autor de un modelo sube otros
pesos, la imagen sigue sirviendo los medidos. Cambiarla es cambiar de
modelo, y las medidas de la ficha se repiten antes (#119). Es ``None`` donde
``model_id`` lo es.

El campo ``dimension`` indica QUÉ mide cada señal, no cómo de transparente es:

- ``form``      — sensacionalismo en la redacción del titular (estilo).
- ``deception`` — que el titular prometa algo que el cuerpo no cumple.
- ``tone``      — carga emocional del texto; no es una señal de clickbait.

Es lo que permite a ``/analyze`` agrupar los veredictos por dimensión en vez de
promediar señales que miden cosas distintas: tres señales de *forma* de acuerdo
no significan que el titular engañe. Sin este campo, el backend tendría que
cablear qué señal es cuál — justo lo que se evita.

DOS PÚBLICOS, Y SÓLO UNO LEE LO QUE SE PUBLICA (#211)

``limitations`` es lo que una señal no sabe hacer, medido: es de quien lee un
resultado, y sale por ``describe_models``, el catálogo y la pantalla de Sistema
(R3.9). ``operation`` es cómo se instala o se sirve —paquetes que
``requirements.txt`` no trae, la vía remota que no existe—: es de quien opera
el sistema, y **no se publica**. Estaban mezclados, y el agente le repetía a
cualquiera que ``torch`` no viene en ``requirements.txt``. Van en la misma ficha
para que, si el modelo cambia, se vean en el mismo sitio; la que se publica la
construye ``factory.ficha_efectiva``, que es la única puerta.

UNA FICHA POR SEÑAL E IDIOMA (#230)

Una señal analiza un idioma si tiene un modelo para él, y cada modelo trae sus
límites medidos, así que la ficha es por señal e idioma: ``language`` dice de
cuál. Toda señal tiene la suya en inglés; en español, sólo las que tengan
modelo propio (en ``v0.8``, el lineal, la dedicada y el tono; la incoherencia
no, porque en español no separa, #233). Lo que describe el HUECO —la dimensión y el
tipo— es el mismo en todos los idiomas, y un test lo exige: el veredicto
agrega por dimensión, y una señal no puede medir otra cosa según el idioma.
"""

from backend.core.idioma import ESPANOL, INGLES, NOMBRES, Idioma
from backend.integrations.nlp.outputs import FichaModelo


class FichaDeclarada(FichaModelo):
    """La ficha tal como se escribe aquí: la publicada más las notas de quien
    opera el sistema (#211), que no salen por ninguna vía pública."""

    operation: list[str]


def model_id_de(signal: str, idioma: Idioma) -> str:
    """El id de HuggingFace de una señal en un idioma, exigiendo que lo tenga.

    ``model_id`` es ``None`` a propósito en el léxico y el lineal, que no son un
    modelo descargable, y ese ``None`` es información. El precio lo pagaba quien
    lo consume: las señales que sí necesitan un modelo lo leían de la ficha y se
    lo pasaban al backend NLP sin comprobar nada.

    Si una ficha perdiera su id, hoy el fallo saldría dentro de la llamada HTTP
    —una URL con ``None`` dentro— y el mensaje no diría de qué señal viene. Aquí
    dice cuál y por qué. Detectado por pyright en #139.

    El idioma es obligatorio (#230): con un valor por defecto, quien lo
    olvidara recibiría el modelo inglés para un titular en español sin que
    nada fallara, que es justo lo que #229 vino a cortar.
    """
    ficha = ficha_declarada(signal, idioma)
    if ficha is None:
        raise ValueError(f"La señal «{signal}» no tiene ficha en {NOMBRES[idioma]}.")
    identificador = ficha["model_id"]
    if identificador is None:
        raise ValueError(f"La señal «{signal}» no usa un modelo descargable.")
    return identificador


def fichas_en(idioma: Idioma) -> dict[str, FichaDeclarada]:
    """Índice de las fichas de un idioma por nombre de tool.

    Vive aquí y no en quien lo usa porque lo necesitan varios consumidores —la
    orquestación de ``/analyze``, para leer la dimensión de cada señal, y el
    catálogo, para adjuntar la ficha— y dos copias del mismo índice acabarían
    divergiendo. Era ``cards_by_signal()`` hasta #230, cuando cada señal pasó
    a poder tener una ficha por idioma.
    """
    return {card["signal"]: card for card in MODEL_CARDS if card["language"] == idioma}


def ficha_declarada(signal: str, idioma: Idioma) -> FichaDeclarada | None:
    """La ficha de una señal en un idioma, o ``None`` si no tiene (#230).

    ``None`` dice que ningún modelo declarado analiza la señal en ese idioma;
    si se ejecuta igual, por configuración o con su motivo de no hacerlo, lo
    decide la factoría.
    """
    return fichas_en(idioma).get(signal)


MODEL_CARDS: list[FichaDeclarada] = [
    {
        "signal": "detect_clickbait",
        "language": INGLES,
        "model_id": "Stremie/roberta-base-clickbait",
        "revision": "517de05db9ba2bf977c6c653d2f03265b74317a8",
        "name": "RoBERTa dedicado (entrenado en Webis-17)",
        "task": "Clasifica el titular como clickbait vs factual con un modelo afinado específicamente para esta tarea.",
        "type": "opaque",
        "dimension": "form",
        "limitations": [
            "Caja negra: sin explicación intrínseca (post-hoc opcional, R3.11).",
            "Solo inglés: el español lo analiza otro modelo, afinado en este proyecto (#242), con su ficha aparte. Entrenado sobre `postText` de Webis-17, es decir TUITS de medios, no titulares de portada.",
            "INDEPENDENCIA DESCONOCIDA, que no es lo mismo que buena: en Chakraborty coincide mucho con el par acoplado (kappa 0.726 con el léxico y 0.772 con el lineal), pero ahí tres clasificadores competentes coinciden por fuerza, así que ese número no informa. Medirla bien exige un corpus con etiqueta humana que el modelo no haya visto — candidato en #121: Webis-Clickbait-16.",
            "SPLIT DE ENTRENAMIENTO DESCONOCIDO: su ficha dice «Webis-Clickbait-17» sin precisar cuál de los dos splits, que son disjuntos. Medido en ambos: F1 0.631 en `train170331` (2459) y 0.758 en `validation170630` (19484). Ninguno de los dos se parece a la puntuación de un modelo evaluado sobre su propio entrenamiento, así que NO se afirma contaminación — pero tampoco se descarta que viera uno de ellos.",
            "Sustituye a `facebook/bart-large-mnli` (#115), elegido en E3-02 por eliminación y medido en #109 al 63.7%. La sustitución sí se decidió por medida: F1 0.946 en Chakraborty — corpus que NO vio — frente al 0.473 del anterior, y con la ambigüedad de `forma` cayendo del 37% al 15%.",
            "A favor, y es lo que más pesa: entrenado con ETIQUETA HUMANA (`truthMean` de anotadores), no por fuente. Es la única señal del sistema con supervisión no sesgada por el medio que publicó el titular — el fallo que #76 destapó y #109 cuantificó.",
            "No memoriza, verificado: rinde MEJOR fuera de su dominio (F1 0.946 en Chakraborty) que dentro (0.631 y 0.758 en los dos splits de Webis), el patrón inverso al de `elozano/bert-base-cased-clickbait-news`, descartado por 99.7% dentro y F1 0.185 fuera.",
            "Ese 0.946 de Chakraborty NO significa que sea mejor ahí (#121): Chakraborty etiqueta por fuente y ese método no puede producir casos dudosos, así que mide sólo la mitad fácil del problema. Restringiendo Webis a los titulares donde los 5 anotadores coinciden — lo más parecido a Chakraborty que hay dentro de Webis — sube a F1 0.906, y el resto lo explica el balance de clases.",
            "Contexto imprescindible para leer cualquiera de estos números: el techo humano de la tarea es F1 0.665, y sólo el 34.9% de los titulares tiene a los 5 anotadores de acuerdo (#121). Sus errores se concentran donde las personas discrepan (92.9% de los fallos en el 65.1% dudoso) y su confianza baja ahí (0.918 vs 0.834), sin haber visto nunca los juicios individuales.",
        ],
        "operation": [
            "NO SE PUEDE SERVIR EN REMOTO, y es permanente: `hf-inference` responde `400 Model not supported by provider`. Detectado el 2026-09-03 al ejecutar la pantalla contra la API de verdad, y confirmado el 2026-09-07 contra el catálogo del proveedor: la ficha del Hub no declara ninguno (`inferenceProviderMapping` vacío) y NINGUNO de los 40 modelos de clickbait del Hub lo tiene. HuggingFace sirve por demanda, y éste tiene 59 descargas/mes frente a los 3.248.238 del de sentimiento, que entonces sí respondía por la misma vía y con el mismo token (desde el 7 oct 2026 da 402, sin crédito: ver su ficha). Doce reintentos en dos minutos no lo reactivan. Con `nlp_backend=remote` esta señal sale SIEMPRE en `error`, y desde el 7 oct el tono también: el veredicto se emite con el léxico, el lineal y la incoherencia, que corren en el propio proceso con cualquier backend.",
            "Y la vía local, que es la única que queda, DEPENDE DE UN PAQUETE QUE `requirements.txt` NO TRAE: `torch`. No es un descuido —es lo que mantiene ligero al CI, que mockea los backends—, así que una instalación hecha sólo con `requirements.txt` no puede ejecutar esta señal por ninguna de las dos vías. El despliegue sí: la imagen instala la rueda CPU-only de torch (#162) y el compose fija `nlp_backend=local` (#164). Medido el 2026-09-08: con esa rueda (769 MB) la señal responde sin GPU, con 1.201 MB de RAM para los tres modelos y 0.11 s por análisis en caliente.",
        ],
        # Era "remote | local" hasta el 2026-09-07. La vía remota no existe: ver
        # la primera nota de operación de arriba.
        "backend": "local",
    },
    {
        "signal": "analyze_sentiment",
        "language": INGLES,
        "model_id": "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "revision": "3216a57f2a0d9c45a2e6c20157c20c49fb4bf9c7",
        "name": "RoBERTa afinado en tuits (3 clases)",
        "task": "Análisis de sentimiento en 3 clases (positivo / neutral / negativo).",
        "type": "opaque",
        "dimension": "tone",
        "limitations": [
            "Entrenado en tuits, no en titulares de noticias.",
            "Caja negra.",
            "Solo inglés: el español lo analiza otro modelo (#233), con su ficha aparte.",
        ],
        "operation": [
            "SIN VÍA REMOTA GRATUITA desde el 7 oct 2026: Hugging Face retiró el crédito mensual de las cuentas gratuitas (en https://huggingface.co/docs/inference-providers/pricing, la fila «Free Users» pasó a «None»; huggingface/hub-docs#2865), y `hf-inference` responde `402` («You have no remaining credits») con la cuenta del proyecto, que es gratuita. No es una caída: con crédito volvería a responder, y por eso la vía remota se conserva. Con `nlp_backend=remote` esta señal sale en `error`; como el tono no vota, el veredicto no cambia. Se repite con `spikes/hf_credito.py` (#236).",
            "La vía local DEPENDE DE `torch`, que `requirements.txt` no trae, como la dedicada: una instalación hecha sólo con `requirements.txt` no puede ejecutar esta señal por ninguna de las dos vías, y lo dice al fallar (#158). El despliegue lo instala (#162) y fija `nlp_backend=local` (#164).",
        ],
        # Era "remote | local" hasta #236 (2026-10-08). La vía remota exige
        # crédito: ver la primera nota de operación de arriba.
        "backend": "local",
    },
    {
        "signal": "detect_clickbait_incoherence",
        "language": INGLES,
        "dimension": "deception",
        "model_id": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
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
        "operation": [
            "DEPENDE DE UN PAQUETE QUE `requirements.txt` NO TRAE: `sentence-transformers`. Y esta señal no tiene vía remota, así que una instalación hecha sólo con `requirements.txt` falla con CUALQUIER `nlp_backend`. La imagen de despliegue lo instala (#162), así que en el despliegue responde; comprobado el 2026-09-08 que ponerlo después de la rueda CPU de torch no la sustituye por la variante CUDA.",
        ],
        "backend": "local",
    },
    {
        "signal": "detect_clickbait_lexical",
        "language": INGLES,
        "dimension": "form",
        # Sin `model_id`: no hay nada que descargar. Son regex y listas de cues.
        "model_id": None,
        "revision": None,
        "name": "Léxico por reglas (listas de cues de Chakraborty et al. 2016)",
        "task": "Detecta pistas léxicas/estructurales de clickbait y devuelve qué cues dispararon y dónde.",
        "type": "interpretable",
        "limitations": [
            "Capta clickbait de forma/estilo, no de engaño semántico.",
            "THRESHOLD=1 agresivo: el veredicto es EXACTAMENTE el indicador «¿disparó algún cue?» — verificado en #109: coincidía con el vector no vacío del lineal de entonces en el 100% de 6400 titulares de dev. El score pesa en la explicación, no en la decisión.",
            "Superficial: no entiende el significado.",
            "No generaliza fuera de dominio sin adaptación — medido: F1 0.843 en titulares de noticias (Chakraborty test) vs 0.498 en tuits (Webis-17).",
            "Techo de recall por cobertura del léxico: el 15.5% de los positivos de Chakraborty dev y el 32.5% de los de Webis-17 no disparan ningún cue, así que son indetectables por construcción (techo 84.5% y 67.5%). #75 amplió los rasgos del lineal (#78), no los de esta señal.",
            "A favor, y medido: su recall sigue el juicio humano de intensidad casi linealmente en Webis-17 (51.6% / 75.8% / 85.5% por tercios de `truthMean`, n=62 por tramo). Es la señal que mejor generalizaba fuera de dominio de las cuatro evaluadas en #109, por delante incluso del lineal de entonces, que se estancaba en los tramos altos (61.3% -> 62.9%).",
            "Solo inglés.",
        ],
        "operation": [],
        "backend": "local",
    },
    {
        "signal": "detect_clickbait_linear",
        "language": INGLES,
        "dimension": "form",
        # Sin `model_id`: los pesos son un JSON del repo, no un modelo de la Hub.
        "model_id": None,
        "revision": None,
        "name": "Regresión logística sobre las palabras del titular (entrenada en Chakraborty, Webis-17 y TA1C)",
        "task": "Clickbait ponderado: aprende el peso de cada palabra y patrón del titular, y devuelve los que más contribuyeron al veredicto.",
        "type": "interpretable",
        "limitations": [
            "Detecta clickbait de ESTILO, no engaño semántico: mira qué palabras usa el titular, no si el cuerpo cumple lo que promete.",
            "Medido por dominio, en titulares que no vio: F1 0.960 en titulares de noticias (Chakraborty test) y 0.523 en tuits (Webis-17, 15.588 de `validation170630`), con umbral 0.35 (#231; para ese test, su segunda apertura). Con el lineal de #78, 0.961 y 0.534; hasta #78, sobre las pistas del léxico, 0.865 y 0.447. Fuera de dominio sigue lejos del techo humano de la tarea en Webis-17 (F1 0.665, #121).",
            "Parte de su acierto en Chakraborty es VOCABULARIO DE FUENTE: allí las etiquetas son por medio (BuzzFeed sí, NYT o WikiNews no), y entre sus pesos fuertes hay `wikinews`, `obama`, `uk` o `china`, que dicen de dónde viene el titular y no si es clickbait. Los años y las marcas de tuit se quitaron al normalizar los rasgos (#78); éstos no se podan a mano.",
            "Desde #78 no está acoplada al léxico por construcción: comparte con él sólo los cuatro patrones de estructura y la manera de partir las palabras. Acuerdo con el léxico: kappa 0.712 en Chakraborty dev y 0.384 en Webis (con el lineal de #78, 0.715 y 0.368; antes de #78, 0.880 y 0.644).",
            "Casi ningún titular se queda sin rasgos (0.5% en Webis-17, antes el 53.3%), y el techo de recall pasa del 65.5% al 98.1%: el límite ya no es el featurizado. Una palabra que no vio al entrenar no cuenta.",
            "La explicación son palabras con su contribución (peso × tf-idf), no pistas de una lista: más cobertura, a cambio de pesos que a veces no se entienden solos (`the` a favor, `in` en contra).",
            "Dos de los cuatro patrones de estructura pesan EN CONTRA (mayúsculas −1.60, elipsis −0.87); la interrogación casi no pesa (+0.43; −1.59 con el lineal de #78), y el número inicial, +12.49: donde el léxico ve una pista de clickbait, el lineal puede restar. Sin medir por qué; las hipótesis son que las palabras interrogativas (`why`, `how`) ya llevan el peso, y que en los tuits de Webis-17 los puntos suspensivos son de recorte y las mayúsculas, de «BREAKING».",
            "Se entrenó con `train170331` de Webis-17: medirla sobre ese split ya no es una validación externa.",
            "Vota con umbral 0.35, no 0.5 (#231): lo eligió la regla de #78 sobre la media de los tres dev (Chakraborty, Webis-17 y TA1C), y es el mismo en los dos idiomas.",
            "Bilingüe desde #231: los mismos pesos analizan el español, con su ficha aparte.",
        ],
        "operation": [],
        "backend": "local",
    },
    {
        "signal": "detect_clickbait_linear",
        "language": ESPANOL,
        "dimension": "form",
        # El mismo modelo que la ficha inglesa: es bilingüe desde #231.
        "model_id": None,
        "revision": None,
        "name": "Regresión logística sobre las palabras del titular (entrenada en Chakraborty, Webis-17 y TA1C)",
        "task": "Clickbait ponderado: aprende el peso de cada palabra y patrón del titular, y devuelve los que más contribuyeron al veredicto.",
        "type": "interpretable",
        "limitations": [
            "Detecta clickbait de ESTILO, no engaño semántico: mira qué palabras usa el titular, no si el cuerpo cumple lo que promete.",
            "Medido en TA1C test (#231), tuits en español: F1 0.674 (P 0.756, R 0.608) con umbral 0.35, frente a 0.61 de la base publicada con el corpus (TF-IDF + XGBoost) y 0.84 de BETO afinado. Hasta #231, con el español tratado como inglés, 0.019 en TA1C validation (#229).",
            "Es el MISMO modelo que analiza el inglés: el bilingüe empató en TA1C validation con uno entrenado sólo con TA1C (0.390 frente a 0.368 con umbral 0.5, dentro del ruido) sin bajar el inglés, y la regla publicada en #231 lo prefería en el empate.",
            "Aprende VOCABULARIO DE FUENTE también en español: nombres de medios y etiquetas de sección pesan en contra (`euvzla` −2.10, `diariolibre` −1.28, `opinión` −1.21, `columna` −0.59), y dicen de dónde viene el tuit, no si es clickbait.",
            "TA1C son tuits con los que 18 medios de 12 países anuncian una noticia, no titulares de portada: fuera de ese registro, sin medir.",
            "El umbral 0.35 es el de los dos idiomas: lo eligió la media de los tres dev. En TA1C validation solo, el mejor corte quedaba por debajo de 0.30, fuera de la rejilla que publicó la regla.",
            "Las mayúsculas con tilde cuentan desde #231 (`ÚLTIMA`, `ESPAÑA`), pero de los 51 tuits de TA1C que las ganan, 42 las ganan por una etiqueta de sección (`#ATENCIÓN`, `#OPINIÓN`); el patrón pesa en contra (−1.60).",
            "Sin acuerdo con el léxico que medir: el léxico no analiza español.",
        ],
        "operation": [],
        "backend": "local",
    },
    {
        "signal": "detect_clickbait",
        "language": ESPANOL,
        "model_id": "ggcastle/beto-clickbait-es",
        "revision": "03c31ac0c288a982fb2aa02755a9bd0abb43078e",
        "name": "BETO afinado en TA1C (entrenado en este proyecto)",
        "task": "Clasifica el titular como clickbait vs factual con un modelo afinado específicamente para esta tarea.",
        "type": "opaque",
        "dimension": "form",
        "limitations": [
            "Caja negra: sin explicación intrínseca (post-hoc opcional, R3.11).",
            "Medido en TA1C test (#242), tuits en español, abierto una vez: F1 0.838 (P 0.899, R 0.784, AUC 0.951), frente a 0.674 del lineal sobre los mismos tuits y 0.84 de BETO afinado según los autores del corpus.",
            "Afinado por este proyecto (#242) desde BETO cased (`dccuchile/bert-base-spanish-wwm-cased`) con los 2.100 tuits de TA1C train, quitando al entrenar las marcas del medio (enlaces, cuentas, etiquetas, corchetes y barras). La receta y la elección de la semilla se fijaron antes de medir. Publicado con su ficha y licencia CC BY 4.0, la de BETO.",
            "RIESGO DE FUENTE acotado, no descartado: los 18 medios de TA1C están en las tres partes, así que test pregunta por medios que ya vio. Con medios fuera (seis pliegues de tres medios, entrenando con los otros quince) da F1 0.808 frente a 0.570 del lineal, el mismo nivel que en validation (0.803): reconocer al medio pesa poco. La limpieza al entrenar casi no cambia el F1 (0.796 limpiando y 0.807 sin limpiar, media de tres semillas en validation).",
            "TA1C son tuits con los que 18 medios de 12 países anuncian una noticia, no titulares de portada: fuera de ese registro, sin medir.",
            "Aprendió de TA1C, como el lineal: si los dos aciertan por la misma pista, su acuerdo no son dos pruebas. Su independencia, sin medir.",
            "Solo español: el inglés lo analiza otro modelo, con su ficha aparte.",
        ],
        "operation": [
            "SIN VÍA REMOTA, como la inglesa: ningún proveedor de Hugging Face lo sirve (`inferenceProviderMapping` vacío, comprobado el 2026-10-09), y desde el 7 oct 2026 la vía remota exige crédito (#236).",
            "La vía local DEPENDE DE `torch`, que `requirements.txt` no trae, como la inglesa; la imagen lo instala (#162). Lo hornea `docker/hornear_modelos.py` desde un repositorio público, sin token: unos 440 MB más. En CPU (Ryzen 5 5600G, 6 hilos), 0.076 s por titular (mediana) y 0.103 s el p95.",
        ],
        "backend": "local",
    },
    {
        "signal": "analyze_sentiment",
        "language": ESPANOL,
        "model_id": "lxyuan/distilbert-base-multilingual-cased-sentiments-student",
        "revision": "cf991100d706c13c0a080c097134c05b7f436c45",
        "name": "DistilBERT multilingüe de sentimiento (3 clases)",
        "task": "Análisis de sentimiento en 3 clases (positivo / neutral / negativo).",
        "type": "opaque",
        "dimension": "tone",
        "limitations": [
            "Caja negra.",
            "Sin evaluación propia: TA1C no trae etiquetas de tono y el tono no vota, así que no hay con qué medirlo (#233). Se lee como una pista más.",
            "Destilado de un zero-shot: aprendió lo que decía `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`, con una plantilla en inglés, sobre un corpus multilingüe de sentimiento cuyas etiquetas humanas se ignoraron a propósito. No aprendió de lo que dicen las personas.",
            "No está entrenado en tuits ni en titulares, al revés que el modelo inglés.",
            "Elegido frente a `cardiffnlp/twitter-xlm-roberta-base-sentiment` (tuits, 1,11 GB, sin licencia en el Hub y sin tokenizador rápido, que habría exigido `sentencepiece` y `protobuf` en la imagen) por su licencia Apache-2.0 declarada y por pesar la mitad (#233).",
            "Solo español: el inglés lo analiza otro modelo, con su ficha aparte.",
        ],
        "operation": [
            "La vía local DEPENDE DE `torch`, que `requirements.txt` no trae, como el tono inglés; la imagen lo instala (#162). Trae tokenizador rápido (`tokenizer.json`), así que no necesita `sentencepiece`. Lo hornea `docker/hornear_modelos.py`: unos 540 MB más.",
            "`hf-inference` lo sirve en remoto (comprobado el 2026-10-09), pero desde el 7 oct 2026 la vía remota exige crédito (#236).",
        ],
        "backend": "local",
    },
]
