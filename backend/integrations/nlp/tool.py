"""
NLP Tool: detección de clickbait en titulares (zero-shot).
"""

import json

from mcp.server.fastmcp import FastMCP
from backend.core.observability import log_tool_invocation
from backend.integrations.nlp.factory import get_nlp_backend


def register(mcp: FastMCP):

    api = get_nlp_backend()

    @mcp.tool()
    @log_tool_invocation
    async def detect_clickbait(headline: str) -> str:
        """Detecta si un titular de noticia es clickbait o informativo (factual).

        Usa clasificación zero-shot (NLI) con las etiquetas fijas "clickbait" y
        "factual news": no necesita un modelo entrenado específicamente en
        clickbait. Pensado para titulares en inglés.

        Args:
            headline (str): titular a evaluar (en inglés).

        Returns:
            JSON con la etiqueta ganadora y su confianza (0-1),
            p.ej. {"label": "clickbait", "score": 0.79}. Devuelve un mensaje
            de error si la llamada al modelo falla.
        """
        response = await api.zero_shot(
            headline,
            "facebook/bart-large-mnli",
            # modelo Zero-SHot para MVP
            ["clickbait", "factual news"],
            # Labels para crear y descartar hipotesis. FIJOS para no confundir LLM.
        )
        if not response.has_content():
            return response.error or "Error al analizar el titular"
        return json.dumps(response.data)

    @mcp.tool()
    @log_tool_invocation
    async def analyze_sentiment(text: str) -> str:
        """Analiza el sentimiento de un texto (p.ej. un titular de noticia).

        Clasifica en tres clases: positive, neutral o negative (modelo en
        inglés, afinado para texto corto). Útil para medir el tono.

        Args:
            text (str): texto a analizar (en inglés).

        Returns:
            JSON con la etiqueta ganadora y su confianza (0-1),
            p.ej. {"label": "neutral", "score": 0.62}. Devuelve un mensaje
            de error si la llamada al modelo falla.
        """
        response = await api.classify(
            text, "cardiffnlp/twitter-roberta-base-sentiment-latest"
        )
        if not response.has_content():
            return response.error or "Error al analizar el sentimiento"
        return json.dumps(response.data)
