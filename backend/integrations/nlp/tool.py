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

from backend.core.observability import log_tool_invocation
from backend.integrations.metadata import tool_meta
from backend.integrations.nlp import dedicated, lexical, linear, model_cards
from backend.integrations.nlp.factory import get_nlp_backend
from backend.integrations.nlp.incoherence import IncoherenceDetector
from backend.integrations.nlp.outputs import (
    Etiqueta,
    FichaModelo,
    SalidaIncoherencia,
    SalidaLexica,
    SalidaLineal,
)


def register(mcp: FastMCP):

    api = get_nlp_backend()
    detector = IncoherenceDetector()

    # Los ids de modelo salen de las fichas (#116), no cableados aquí. Se
    # resuelven una vez al registrar y no en cada llamada: MODEL_CARDS es una
    # constante de módulo, así que releerla por invocación sería trabajo inútil.
    _ficha = model_cards.cards_by_signal()

    @mcp.tool(meta=tool_meta("Señales de análisis", __name__))
    @log_tool_invocation
    async def detect_clickbait(headline: str) -> Etiqueta:
        """Detecta si un titular de noticia es clickbait o informativo (factual).

        Usa un modelo afinado específicamente para esta tarea sobre anotaciones
        humanas, no una clasificación genérica. Complementaria a
        `detect_clickbait_lexical` y `detect_clickbait_linear`, que miran pistas
        de superficie y sí explican su veredicto. Pensada para inglés.

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
        response = await dedicated.detect(api, headline)
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
        response = await api.classify(
            text, model_cards.model_id_de("analyze_sentiment")
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
        noticia → señal de clickbait. Es complementaria a `detect_clickbait`
        (que solo mira el estilo del titular): esta necesita además el cuerpo
        o teaser. Pensada para texto en inglés.

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
        response = await detector.detect(headline, content)
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
        explicación), complementaria a `detect_clickbait` (zero-shot) y
        `detect_clickbait_incoherence`. Pensada para titulares en inglés.

        Args:
            headline (str): titular a evaluar (en inglés).

        Returns:
            `score` (nº de pistas), `is_clickbait` (score ≥ umbral), `matches`
            (lista de {category, cue, span}) y `headline`.

        Raises:
            Si el titular está vacío.
        """
        response = lexical.detect(headline)
        if not response.has_content():
            raise ToolError(response.error or "Error al analizar léxico en el titular")
        return response.unwrap()

    @mcp.tool(meta=tool_meta("Señales de análisis", __name__))
    @log_tool_invocation
    async def detect_clickbait_linear(headline: str) -> SalidaLineal:
        """Detecta clickbait con un modelo lineal interpretable (regresión logística
        entrenada sobre pistas léxicas).

        Args:
            headline: el titular a analizar.

        Returns:
            `is_clickbait`, `probability` y `top_cues` — los cues que más
            empujaron el veredicto (peso × frecuencia), como explicación
            intrínseca (R3.8). Cuarta señal contrastable frente a zero-shot,
            incoherencia y léxico.

        Raises:
            Si el titular está vacío.
        """
        response = linear.predict(headline)
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
        return model_cards.MODEL_CARDS
