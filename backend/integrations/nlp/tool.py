"""
NLP Tool: detección de clickbait en titulares.

Cada tool declara su tipo de salida, así que MCP publica un ``outputSchema`` y
el cliente recibe el objeto estructurado en vez de una cadena que tenga que
parsear. Y los fallos se **lanzan**: el protocolo los marca con ``isError``, en
vez de devolver el mensaje por el mismo canal que un resultado válido — que era
indistinguible desde fuera.
"""

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from backend.core.idioma import INGLES, Idioma, detectar
from backend.core.observability import log_tool_invocation
from backend.core.texto import es_ausente
from backend.integrations.metadata import tool_meta
from backend.integrations.nlp import dedicated, lexical, linear, model_cards
from backend.integrations.nlp.factory import (
    ficha_efectiva,
    get_incoherence_detector,
    get_invocacion,
    get_model_id,
    get_nlp_backend,
    get_threshold,
    get_top_cues,
    idiomas_de,
    motivo_si_el_cuerpo_no_se_compara,
    motivo_si_no_se_analiza,
)
from backend.integrations.nlp.outputs import (
    Etiqueta,
    FichaModelo,
    SalidaIncoherencia,
    SalidaLexica,
    SalidaLineal,
)


def _idioma_si_se_analiza(signal: str, texto: str) -> Idioma:
    """El idioma del titular, si la señal lo analiza; si no, corta con el motivo.

    La misma puerta que `_run_signals`, para quien llama a una señal suelta: el
    agente por MCP, o Sistema por `/tools/{name}/execute`. La frase sale de la
    factoría, así que las dos fachadas dicen lo mismo (#116).

    Desde #230 es por señal y devuelve el idioma: con él pide cada herramienta
    a la factoría su modelo y su umbral. Hasta entonces era una puerta para
    todas a la vez (#229).
    """
    idioma = detectar(texto)
    if motivo := motivo_si_no_se_analiza(signal, idioma):
        raise ToolError(motivo)
    return idioma


def register(mcp: FastMCP):

    # Ni el backend ni el detector se crean aquí. Los pide la factoría en cada
    # llamada, que los cachea: así siguen siendo instancias únicas —cargar un
    # modelo cuesta— pero dejan de quedarse atados a la configuración que hubiera
    # al registrar. Antes, cambiar `nlp_backend` después de arrancar no tenía
    # efecto en esta fachada (#87).
    #
    # Los ids salen de la ficha (#116) y de la configuración si la hay (#119),
    # y también por llamada: una constante aquí volvería a congelarlos. Lo
    # mismo los umbrales y el tope de pistas del lineal (#93).

    @mcp.tool(meta=tool_meta("Señales de análisis", __name__))
    @log_tool_invocation
    async def detect_clickbait(headline: str) -> Etiqueta:
        """Clasifica un titular como clickbait o noticia factual con un modelo de caja negra.

        Por defecto es un clasificador neuronal afinado para esta tarea sobre
        titulares anotados por personas, fuera de este proyecto; por
        configuración puede ser otro, también un zero-shot que elige entre
        etiquetas que se le dan (`describe_models` dice cuál). Devuelve una
        etiqueta y la confianza del modelo en ESA etiqueta, sin explicar por
        qué: no es una probabilidad de
        clickbait (con "factual news" y 0.9, lo que afirma es que NO lo es).
        Si hace falta una probabilidad de clickbait o saber qué la explica, lo
        da `detect_clickbait_linear`; qué pistas aparecen y dónde,
        `detect_clickbait_lexical`. Pensada para inglés.

        Args:
            headline (str): titular a evaluar (en inglés).

        Returns:
            La etiqueta ganadora y su confianza (0-1), p.ej.
            {"label": "clickbait", "score": 0.79}. Las etiquetas son siempre
            "clickbait" o "factual news", con independencia del modelo que haya
            detrás.

        Raises:
            Si la llamada al modelo falla (timeout o caída del proveedor).
        """
        idioma = _idioma_si_se_analiza("detect_clickbait", headline)
        # El modelo, el modo y las etiquetas, de la configuración (#159), los
        # del idioma del titular (#230).
        invocacion = get_invocacion("detect_clickbait", idioma)
        response = await dedicated.detect(
            get_nlp_backend(),
            headline,
            invocacion.id,
            invocacion.task,
            invocacion.labels,
        )
        if not response.has_content():
            raise ToolError(response.error or "Error al analizar el titular")
        return response.unwrap()

    @mcp.tool(meta=tool_meta("Señales de análisis", __name__))
    @log_tool_invocation
    async def analyze_sentiment(text: str) -> Etiqueta:
        """Analiza el sentimiento de un texto (p.ej. un titular de noticia).

        Clasifica en tres clases: positive, neutral o negative (modelo en
        inglés, afinado para texto corto). Útil para medir el tono.

        Args:
            text (str): texto a analizar (en inglés).

        Returns:
            La etiqueta ganadora y su confianza (0-1), p.ej.
            {"label": "neutral", "score": 0.62}.

        Raises:
            Si la llamada al modelo falla (timeout o caída del proveedor).
        """
        idioma = _idioma_si_se_analiza("analyze_sentiment", text)
        response = await get_nlp_backend().classify(
            text, get_model_id("analyze_sentiment", idioma)
        )
        if not response.has_content():
            raise ToolError(response.error or "Error al analizar el sentimiento")
        return response.unwrap()

    @mcp.tool(meta=tool_meta("Señales de análisis", __name__))
    @log_tool_invocation
    async def detect_clickbait_incoherence(
        headline: str, content: str
    ) -> SalidaIncoherencia:
        """Detecta posible clickbait midiendo la (in)coherencia entre titular y cuerpo.

        Genera embeddings del titular y del contenido con un modelo de
        sentence-transformers y calcula su similitud del coseno. Una similitud
        baja indica que el titular no se corresponde con lo que cuenta la
        noticia → señal de clickbait. Es complementaria a las señales que sólo
        miran el titular (`detect_clickbait`, `detect_clickbait_lexical` y
        `detect_clickbait_linear`): esta necesita además el cuerpo o teaser.
        Pensada para texto en inglés.

        Args:
            headline (str): titular a evaluar (en inglés).
            content (str): cuerpo o teaser de la noticia con el que contrastar.

        Returns:
            La similitud (0-1), si se considera incoherente (`incoherent` a true
            cuando está por debajo del umbral) y los textos comparados, p.ej.
            {"similarity": 0.18, "incoherent": true, "headline": "...",
            "content": "..."}.

        Raises:
            Si el cálculo de los embeddings falla.
        """
        # El idioma antes que el cuerpo, como en `_run_signals`: con un titular
        # que no se analiza, pedir el cuerpo sería una pista falsa (#229).
        idioma = _idioma_si_se_analiza("detect_clickbait_incoherence", headline)
        # Un cuerpo que sólo dice «None» no es un cuerpo (#197): medir la
        # similitud contra esa palabra daría un «incoherente» inventado. El
        # error vuelve al modelo del agente para que lo corrija.
        if es_ausente(content):
            raise ToolError(
                "Hace falta el cuerpo o el teaser de la noticia para medir la "
                "incoherencia; sin él, esta señal no se puede aplicar."
            )
        # Ni un cuerpo en un idioma que no compara: el modelo que los compara es
        # de un idioma (`motivo_si_el_cuerpo_no_se_compara` dice por qué, #229).
        motivo_del_cuerpo = motivo_si_el_cuerpo_no_se_compara(detectar(content))
        if motivo_del_cuerpo:
            raise ToolError(motivo_del_cuerpo)
        response = await get_incoherence_detector(idioma).detect(headline, content)
        if not response.has_content():
            raise ToolError(
                response.error or "Error al analizar incoherencia en el titular"
            )
        return response.unwrap()

    @mcp.tool(meta=tool_meta("Señales de análisis", __name__))
    @log_tool_invocation
    async def detect_clickbait_lexical(headline: str) -> SalidaLexica:
        """
        Detecta clickbait por pistas léxicas y estructurales del titular (señal explicable).

        Busca marcas típicas de clickbait —hipérbole, referencias vagas (this/these),
        frases gancho, número inicial (listicle), interrogación, mayúsculas, elipsis—
        y devuelve qué pistas dispararon y dónde. Señal white-box (la evidencia ES la
        explicación), complementaria a `detect_clickbait` (caja negra), a
        `detect_clickbait_linear` (que pondera las palabras del titular) y a
        `detect_clickbait_incoherence`. Pensada para titulares en inglés.

        Args:
            headline (str): titular a evaluar (en inglés).

        Returns:
            `score` (nº de pistas), `is_clickbait` (score ≥ umbral), `matches`
            (lista de {category, cue, span}) y `headline`.

        Raises:
            Si el titular está vacío.
        """
        idioma = _idioma_si_se_analiza("detect_clickbait_lexical", headline)
        response = lexical.detect(
            headline, get_threshold("detect_clickbait_lexical", idioma)
        )
        if not response.has_content():
            raise ToolError(response.error or "Error al analizar léxico en el titular")
        return response.unwrap()

    @mcp.tool(meta=tool_meta("Señales de análisis", __name__))
    @log_tool_invocation
    async def detect_clickbait_linear(headline: str) -> SalidaLineal:
        """Da la probabilidad de que un titular sea clickbait y las pistas que la explican.

        Es el modelo entrenado en este proyecto: una regresión logística sobre
        las palabras del titular y su estructura (número inicial,
        interrogación…), en la que cada palabra tiene un peso visible. El
        veredicto se explica con las que más pesaron. Para la opinión de un
        modelo sin pesos visibles, `detect_clickbait` (caja negra). Pensada
        para inglés.

        Args:
            headline (str): titular a evaluar (en inglés).

        Returns:
            `is_clickbait`, `probability` (0-1, de que sea clickbait), `top_cues`
            —las palabras que más empujaron el veredicto (peso × tf-idf), que
            son su explicación intrínseca (R3.8)— y `headline`.

        Raises:
            Si el titular está vacío.
        """
        # Sin idioma para el detector: hoy sólo hay pesos en inglés, y la puerta
        # no deja llegar otro. Los del español, en #231.
        _idioma_si_se_analiza("detect_clickbait_linear", headline)
        response = linear.predict(headline, get_top_cues())
        if not response.has_content():
            raise ToolError(response.error or "Error al predecir clickbait")
        return response.unwrap()

    # Utilidad, no señal: describe los modelos, no analiza nada. Es el caso que
    # demuestra que la categoría no se puede derivar del paquete.
    @mcp.tool(meta=tool_meta("Utilidades", __name__))
    @log_tool_invocation
    async def describe_models() -> list[FichaModelo]:
        """Divulga los modelos/señales que emplea el sistema (transparencia, R3.9).

        Devuelve, por cada señal, su nombre, tarea, tipo (interpretable /
        híbrido / opaco), dimensión que mide y limitaciones conocidas. Sin
        argumentos. Útil para la transparencia de sistema y para decidir qué
        señal usar según su naturaleza (white-box vs caja negra) y sus límites.

        Returns:
            La lista de fichas de modelo (signal, name, task, type, dimension,
            limitations, backend).
        """
        # La ficha EFECTIVA, no la declarada: si alguien ha puesto otro modelo
        # por configuración, esto publica ese id y deja de publicar unas medidas
        # que eran del anterior (#119).
        #
        # Y desde #230, una por cada idioma que analiza cada señal (`idiomas_de`,
        # la misma regla que la puerta): la de un modelo que no se ejecuta no
        # sale, y la de uno puesto por configuración en español, sí.
        return [
            ficha_efectiva(senal, idioma)
            for senal in model_cards.fichas_en(INGLES)
            for idioma in idiomas_de(senal)
        ]
