import asyncio

from backend.core.models import ToolResult
from backend.integrations.nlp.model_cards import model_id_de


class IncoherenceDetector:
    # El id sale de la ficha (#116). Antes estaba aquí como "all-MiniLM-L6-v2",
    # SIN el prefijo `sentence-transformers/` que sí llevaba la ficha: dos
    # cadenas distintas para el mismo modelo. Resolvían igual —la librería busca
    # los nombres desnudos en su propia organización—, así que la divergencia no
    # rompía nada y podía sobrevivir indefinidamente mientras la divulgación
    # decía una cosa y el código cargaba otra. Es el caso exacto que motiva #116.
    MODEL = model_id_de("detect_clickbait_incoherence")

    # Similitud POR DEBAJO de esto = incoherente = posible clickbait. Ojo al
    # sentido, que es el contrario del habitual y confunde a quien lo lee rápido.
    #
    # El valor era una estimación sin contrastar. Calibrado en #92 sobre 19.484
    # pares titular↔cuerpo de Webis-17, eligiendo el umbral en una mitad y
    # midiéndolo en la otra, resulta que la estimación era buena: de toda la
    # curva es el punto de mayor precisión (0,649 en test), a cambio de
    # pronunciarse sólo en el 7,4 % de los titulares.
    #
    # Se conserva justamente por eso. `deception` PISA a `form` en la jerarquía de
    # `_overall`, así que un falso positivo suyo declara «engañoso» anulando a
    # las otras tres señales: aquí la precisión pesa más que el recall, y los
    # umbrales más generosos la hunden (0,516 con 0,46; 0,412 con 0,56).
    #
    # Reproducible: python -m backend.evaluation.eval_incoherencia
    THRESHOLD = 0.3

    # El modelo trunca a 256 tokens haga lo que haga quien le pase el texto, y
    # los cuerpos reales miden ~959: el 84 % se descartaba EN SILENCIO, cortado
    # además a mitad de frase. Recortar aquí no cambia el resultado —medido en
    # #92: trocear el artículo entero y quedarse con la mayor similitud da 0,717
    # de AUC frente a 0,716 truncando— pero convierte un límite invisible en uno
    # explícito, y corta por donde termina una frase en vez de por donde acaba
    # un token. ~4 caracteres por token en inglés.
    LEAD_CHARS = 1000

    def __init__(self) -> None:
        self._model = None  # Singleton

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL)
        return self._model

    @classmethod
    def _lead(cls, content: str) -> str:
        """Recorta el cuerpo a lo que el modelo va a leer de todas formas.

        Corta por final de frase, no por carácter: media frase produce un
        embedding que no representa nada, y ese ruido entra en la similitud como
        si fuera contenido.
        """
        if len(content) <= cls.LEAD_CHARS:
            return content
        recorte = content[: cls.LEAD_CHARS]
        fin = recorte.rfind(". ")
        # Si no hay ningún punto en la segunda mitad, cortar por la frase dejaría
        # un texto ridículamente corto: en ese caso vale más el corte crudo.
        return recorte[: fin + 1] if fin > cls.LEAD_CHARS // 2 else recorte

    async def detect(self, headline: str, content: str) -> ToolResult:
        try:
            model = self._get_model()
            embedding = await asyncio.to_thread(
                model.encode, [headline, self._lead(content)]
            )

            # Usa coseno por debajo
            sim = model.similarity(embedding[0], embedding[1]).item()
            # Devuelve tensors, necesitamos .item

            # Tensors: Array de Números de N dimensiones. En este caso 2 embeddings x 1-D Tensor de 384 floats de los cuales reducimos a 1 float x 1 Tensor con similarity (y que extraemos con item)

            inc = sim < self.THRESHOLD
            return ToolResult.ok(
                {
                    "similarity": sim,
                    "incoherent": inc,
                    # El umbral VIAJA con el resultado (#133). Ésta es la señal
                    # híbrida del sistema, y su tesis es que la decisión es
                    # transparente —un corte legible— aunque el rasgo sea opaco.
                    # Una tarjeta que dijera «similitud 0,62 · coherente» sin
                    # enseñar contra qué se comparó pierde exactamente eso.
                    #
                    # Y cablearlo en la interfaz sería peor que copiarlo: #93
                    # propone parametrizar este número, así que se estaría
                    # duplicando un valor que ya está previsto que cambie.
                    "threshold": self.THRESHOLD,
                    "headline": headline,
                    "content": content,
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Error inesperado calculando incoherencia: {e}")
