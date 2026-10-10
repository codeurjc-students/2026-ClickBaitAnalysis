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
        "Elegir herramienta, razonando, con el catálogo real de 12 herramientas y `num_ctx` 8192: 25/26 y 24/26 en dos tandas (#188). Los fallos piden una herramienta real que sobraba, o `analyze_headline` en vez de la señal concreta. El 20/20 de #183 se midió también razonando, sin saberlo, y con 11 herramientas. Con la ventana a 2048 el catálogo se recortaba en silencio, y acertaba 9/20 (spike rehecho en la A40, PR #176). Con las 14 herramientas de `v0.8` y las condiciones de producción (`05-llano`, `num_ctx` 16384, el perfil preciso), 99 de 104 en cuatro pasadas, frente a 101 con el catálogo de `v0.7.0` en la misma sesión (#234); el fallo que se repite es «¿Por qué es difícil detectar clickbait en español?», que pide `describe_models`.",
        "Fidelidad al narrar: razonando, 9 de 9 consultas completas cuentan lo que devolvieron las herramientas, cotejadas a mano con sus datos (#188), y 0 errores en 6 respuestas del spike (PR #176). Es una muestra pequeña. Copia los decimales enteros, y una vez rellenó un parámetro opcional con la cadena «None», que la herramienta tomó como texto (#188). El modelo de 2B se inventó detalles en las dos respuestas que se leyeron (PR #176).",
        "Fidelidad según el prompt y el muestreo, en 27 consultas juzgadas por `gemma4:31b` —calibrado contra lectura a mano, kappa 0,77— y con lo que marcó leído por el autor (#192). Con el muestreo del Modelfile (temperatura 1, `presence_penalty` 1,5): 3 respuestas infieles con `04-preciso` y 5 con `05-llano`. Con el perfil preciso (0,6 y 0) y `05-llano`, que es como lo usa el agente: 1 de 27. Es una sola repetición, y lo que el juez dio por fiel no se leyó (en su calibración dejó pasar 4 infieles de 24). El fallo que queda es de atribución: nombra con las categorías del detector léxico palabras que sólo dio el modelo lineal.",
        "Con historial se inventaba el análisis: con los turnos anteriores sólo como texto, trae la noticia y narra un veredicto con cifras sin llamar a ninguna señal (10 de 20 veces con una conversación de 14 turnos; 0 de 12 sin historial). Por eso el agente avisa de que de esos turnos sólo queda el texto y los monta con los nombres de las herramientas que usaron: con las dos cosas, 0 de 60, con noticias de NYT y de Guardian (#192). En la comprobación de #208, con esa misma configuración, se lo inventó 1 vez de 40: trajo la noticia y narró cifras de señales que no había ejecutado.",
        "Con historial, a veces escribe la respuesta dentro del razonamiento y no la saca: 3 de 57 conversaciones en #192 y 5 de 40 en #208. El agente se la pide una vez más. Con eso y el tope quedaron 2 de 40, y en las dos la vuelta extra también se desbocó. La pantalla enseña entonces las tarjetas sin texto (#208).",
        "A «¿por qué?» después de analizar un titular, en 6 de 20 no llama a ninguna herramienta: dice que los resultados anteriores ya no están y pregunta si debe analizarlo otra vez, aunque tenga el titular en el historial. Un aviso que le pedía volver a llamar a las herramientas no cambió nada (5 de 20; #208).",
        "Lento: razonando, 6–24 s por consulta completa en la A40 (mediana 17,8 s en seis, #188), aunque una llegó a 94 s porque una sola vuelta generó 2.812 tokens; más ~36 s si el servidor arranca en frío (#181). Con un historial de 14 turnos, alguna última vuelta razonó entre 116 y 311 s, y una agotó el corte de 300 s por llamada y la conversación falló (#192). Desde #208, cada vuelta tiene un tope de 1.500 tokens de salida, que acota las desbocadas sin evitarlas. En 40 conversaciones con el historial máximo, la más larga bajó de 313 a 117 s y no falló ninguna, a cambio de una mediana algo mayor (4 s más con NYT y 15 s más con Guardian). Y sólo está disponible mientras hay una sesión abierta en la máquina de la GPU.",
        "Con titulares en español (#234): en cuatro pasadas eligió bien 23 de 24 consultas, y las de noticias en español 8 de 8, sin traducir nunca el titular al pasarlo a una herramienta. En una conversación que pedía una noticia en español y si su titular era clickbait, trajo la noticia y narró un análisis que no había ejecutado: una de las dos veces que se pidió, el fallo que ya se vio en #208. La conversación se ha probado en castellano, que es como se escribieron las consultas de los spikes.",
    ],
}
