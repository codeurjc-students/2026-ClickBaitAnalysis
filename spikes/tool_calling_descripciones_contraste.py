"""Descripciones de clickbait (2026-09-24) - Consultas de CONTRASTE.

Con la ventana entera, la fase 5 sólo fallaba dos consultas —«dame la
probabilidad…» y «usa el modelo entrenado…»—, que elegían `detect_clickbait` en
vez de `detect_clickbait_linear`. Al reescribir los docstrings para separar las
dos herramientas, las palabras de esas consultas acaban dentro de la
descripción nueva, y medir sólo con ellas no distingue entre arreglar la
interfaz y aprender el examen.

Por eso estas seis consultas no dicen ni «probabilidad» ni «entrenado», y están
repartidas: tres deben ir a la lineal y tres a `detect_clickbait`, para cazar
también el fallo contrario — que el docstring nuevo lo mande todo a la lineal.

Límite que no se puede quitar: las consultas y los docstrings los escribió el
mismo autor el mismo día. No es una prueba ciega.

Reutiliza la fase 5 tal cual —el catálogo se pide al servidor por
``list_tools`` y el criterio de acierto es el mismo—; sólo cambia la lista de
consultas.

Ejecutar:  OLLAMA_HOST=127.0.0.1:11500 python spikes/tool_calling_descripciones_contraste.py [modelo] [num_ctx]
"""

import sys
from pathlib import Path

# El spike vive fuera de los paquetes del proyecto; se añade la raíz al path
# para poder importar la fase 5 y, a través de ella, las herramientas reales.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spikes import tool_calling_fase5_descripciones_reales as fase5  # noqa: E402

LINEAL = {"detect_clickbait_linear"}
CAJA_NEGRA = {"detect_clickbait"}

CONSULTAS = [
    ("ESPECIFICA", "¿Cuántas papeletas tiene 'You Won't Guess What She Did' de ser clickbait, en porcentaje?", LINEAL),
    ("ESPECIFICA", "Puntúa 'Ten Foods Doctors Never Eat' y dime qué pistas pesan más en la nota", LINEAL),
    ("ESPECIFICA", "¿Con qué peso contribuye cada palabra de 'Amazing Secrets Revealed' al veredicto?", LINEAL),
    ("ESPECIFICA", "Quiero la opinión de un modelo de caja negra sobre 'Stocks Fall After Fed Decision'", CAJA_NEGRA),
    ("ESPECIFICA", "Sin explicaciones, sólo el veredicto de la red neuronal: 'This Dog Will Melt Your Heart'", CAJA_NEGRA),
    ("ESPECIFICA", "Clasifica '5 Signs You Need a Vacation' con el clasificador afinado sobre anotación humana", CAJA_NEGRA),
]


if __name__ == "__main__":
    fase5.PRUEBAS = CONSULTAS
    fase5.main()
