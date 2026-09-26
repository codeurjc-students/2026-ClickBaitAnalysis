"""La ficha del modelo que usa el agente (R13.7).

Como las de las señales (`nlp/model_cards.py`), dice qué es el modelo, de qué
tipo, y sus limitaciones MEDIDAS, cada una con la issue o la PR donde se midió.
Y como allí, las medidas son de UN modelo: si se configura otro,
`factory.ficha_efectiva` publica el configurado y deja de publicarlas (#119).

La tarea dice ya que el veredicto no es suyo (R13.4), porque eso describe el
HUECO que ocupa el modelo en el sistema, no al modelo: sobrevive a cambiarlo.
"""

from typing import Literal, TypedDict


class FichaLLM(TypedDict):
    """La ficha del modelo de lenguaje. No tiene dimensión: no es una señal."""

    model_id: str
    name: str
    task: str
    type: Literal["opaque"]
    limitations: list[str]


FICHA: FichaLLM = {
    "model_id": "qwen3.5:27b",
    "name": "Qwen 3.5, 27B, servido por Ollama",
    "task": "Entiende la consulta, elige qué herramientas usar y narra lo que devuelven. No emite el veredicto: sale de las herramientas, y las tarjetas se pintan con su resultado, no con el texto del modelo (R13.4).",
    "type": "opaque",
    "limitations": [
        "Caja negra: no explica por qué elige una herramienta ni por qué redacta lo que redacta. Lo que sí se puede comprobar es lo que hace —la traza de herramientas y sus resultados—, y se enseña aparte.",
        "Sin razonar, se inventa el resultado de las herramientas. Con `think: false` eligió bien 13 de 26 consultas, y en 11 de los 13 fallos atribuyó a herramientas que no había llamado resultados que no existen, 8 de ellos con cifras o posiciones inventadas (#188). Por eso el agente le pide razonar siempre.",
        "Elegir herramienta, razonando, con el catálogo real de 12 herramientas y `num_ctx` 8192: 25/26 y 24/26 en dos tandas (#188). Los fallos piden una herramienta real que sobraba, o `analyze_headline` en vez de la señal concreta. El 20/20 de #183 se midió también razonando, sin saberlo, y con 11 herramientas. Con la ventana a 2048 el catálogo se recortaba en silencio, y acertaba 9/20 (spike rehecho en la A40, PR #176).",
        "Fidelidad al narrar: razonando, 9 de 9 consultas completas cuentan lo que devolvieron las herramientas, cotejadas a mano con sus datos (#188), y 0 errores en 6 respuestas del spike (PR #176). Es una muestra pequeña. Copia los decimales enteros, y una vez rellenó un parámetro opcional con la cadena «None», que la herramienta tomó como texto (#188). El modelo de 2B se inventó detalles en las dos respuestas que se leyeron (PR #176).",
        "Lento: razonando, 6–24 s por consulta completa en la A40 (mediana 17,8 s en seis, #188), aunque una llegó a 94 s porque una sola vuelta generó 2.812 tokens; más ~36 s si el servidor arranca en frío (#181). Y sólo está disponible mientras hay una sesión abierta en la máquina de la GPU.",
        "Las herramientas de clickbait están pensadas para titulares en inglés. La conversación se ha probado en castellano, que es como se escribieron las consultas de los spikes.",
    ],
}
