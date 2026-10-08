"""Señal interpretable: una regresión logística sobre las palabras del titular.

Desde #78 (con #75), sus rasgos son las palabras del titular, cada número como
`<number>` y los cuatro patrones de estructura del léxico (número inicial,
interrogación, mayúsculas, elipsis), ponderados con TF-IDF. Se entrena con el
`train` de Chakraborty y con `train170331` de Webis-17
(`evaluation/train_linear.py`); la combinación salió de comparar cuatro
featurizaciones en `evaluation/eval_reentreno.py`.

Desde #231 es BILINGÜE: los mismos pesos para el inglés y el español,
entrenados también con el `train` de TA1C, porque ganaron a unos sólo para el
español en `evaluation/eval_lineal_es.py`. Y vota con el UMBRAL que guarda el
JSON (0,35), no con un 0,5 fijo: lo eligió la regla de #78 sobre los tres
`dev`, así que viaja con los pesos con los que se eligió. Sale en el resultado,
como el del léxico (#93).

Hasta #78 puntuaba las pistas del léxico, y la mitad de los titulares salía con
el vector vacío: «no clickbait» sin haber mirado nada, y un techo de recall del
66 % en Webis. Aquel modelo se conserva en `evaluation/lineal_pistas.py`.

La inferencia es Python puro —el TF-IDF y `sigmoid(w·x + b)` con los valores
de `linear_clickbait.json`, sin sklearn ni torch—. Que calcule lo mismo que el
entrenamiento lo vigila una comprobación guardada en el propio JSON
(`tests/integrations/test_lineal.py`). Devuelve la probabilidad y los rasgos
que más la empujaron (peso × tf-idf), que son su explicación (R3.8).
"""

import json
import math
import re
from collections import Counter
from functools import cache
from pathlib import Path

from backend.core.models import ToolResult
from backend.integrations.nlp import lexical

JSON_FILE = Path(__file__).resolve().parent / "linear_clickbait.json"

# Cuántas pistas se devuelven como explicación. Sólo recorta lo que se ENSEÑA:
# la probabilidad suma todas. Es el defecto (#93): el que se usa lo pasa la
# factoría desde la configuración (`nlp_linear_top_cues`).
TOP_CUES = 20

# Lo que se quita antes de partir en palabras (#78). Webis-17 son tuits, y sus
# convenciones —`RT`, menciones, enlaces— son formato, no titular. Y cada número
# pasa a ser `<number>`: con los números tal cual, los pesos aprendían años
# (`2015` a favor, `2008` en contra), que dicen algo de la época de cada corpus
# y nada del clickbait de un titular cualquiera.
ENLACE = re.compile(r"https?://\S+|www\.\S+")
MENCION = re.compile(r"@\w+")
RETUIT = re.compile(r"\bRT\b")
NUMERO = re.compile(r"\d+(?:[.,]\d+)*")


# Los pesos se leen en el PRIMER USO, no al importar (#108). Leerlos a nivel de
# módulo hacía que importar la señal —aunque fuera para inspeccionarla— abriera
# y parseara el fichero, y fallara si no estaba. Es el patrón de `local.py` y
# `incoherence.py` con sus modelos; aquí basta una lectura cacheada.
@cache
def pesos() -> dict:
    """El intercepto, y el peso y el idf de cada rasgo, tal como los serializó
    `evaluation/train_linear.py`, con su comprobación."""
    with open(JSON_FILE, encoding="utf-8") as fichero:
        return json.load(fichero)


def rasgos(titular: str) -> list[str]:
    """Los rasgos del titular: sus palabras, sus números y sus patrones.

    Es la ÚNICA definición: la usan el entrenamiento (como analizador de
    `TfidfVectorizer`) y la señal. Las palabras se parten como en el léxico
    (`lexical.TOKEN`), en minúsculas. Los patrones van con nombre propio
    (`<question>`), que no choca con ninguna palabra, y se miran sobre el
    titular sin pasar a minúsculas, que es donde se ven las mayúsculas.
    """
    limpio = RETUIT.sub(" ", MENCION.sub(" ", ENLACE.sub(" ", titular)))
    numeros = ["<number>"] * len(NUMERO.findall(limpio))
    palabras = lexical.TOKEN.findall(NUMERO.sub(" ", limpio).lower())
    patrones = [
        f"<{nombre}>"
        for nombre, patron in lexical.PATTERNS.items()
        if patron.search(limpio)
    ]
    return palabras + numeros + patrones


def vectorizar(titular: str) -> dict[str, float]:
    """El TF-IDF del titular sobre el vocabulario aprendido.

    Lo mismo que `TfidfVectorizer` con sus valores por defecto: cuántas veces
    aparece cada rasgo por su idf, y el vector normalizado a longitud 1. Un
    rasgo que el modelo no vio al entrenar no cuenta, y si no queda ninguno el
    vector sale vacío.
    """
    idf = pesos()["idf"]
    cuentas = Counter(rasgo for rasgo in rasgos(titular) if rasgo in idf)
    valores = {rasgo: cuenta * idf[rasgo] for rasgo, cuenta in cuentas.items()}
    norma = math.sqrt(sum(valor**2 for valor in valores.values()))
    if norma == 0:
        return {}
    return {rasgo: valor / norma for rasgo, valor in valores.items()}


def predict(headline, top_cues: int = TOP_CUES) -> ToolResult:
    if not headline or not headline.strip():
        return ToolResult.fail("El titular está vacío o no es válido")

    modelo = pesos()
    # La contribución de cada rasgo es su peso por su tf-idf: la explicación
    # (R3.8) es exactamente la suma que da la probabilidad, ordenada.
    contribuciones = sorted(
        (
            (rasgo, modelo["weights"][rasgo] * valor)
            for rasgo, valor in vectorizar(headline).items()
        ),
        key=lambda par: par[1],
        reverse=True,
    )
    z = modelo["intercept"] + sum(contribucion for _, contribucion in contribuciones)
    probabilidad = 1 / (1 + math.exp(-z))
    # El umbral, del JSON (#231): lo eligió la medida con estos pesos, y
    # cambiar uno sin el otro sería votar con un corte que nadie midió.
    umbral = modelo["threshold"]
    return ToolResult.ok(
        {
            "is_clickbait": probabilidad >= umbral,
            "probability": probabilidad,
            "threshold": umbral,
            "top_cues": contribuciones[:top_cues],  # Las que más empujaron
            "headline": headline,
        }
    )
