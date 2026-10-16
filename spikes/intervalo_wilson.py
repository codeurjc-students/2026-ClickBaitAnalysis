"""#269 (2026-10-16) - El intervalo de confianza de una proporción pequeña.

Con 16 o 26 casos, «1 de 16» o «98 de 104» no son una tasa: son una muestra
pequeña, y la tasa de verdad puede estar lejos. Este guion da el intervalo de
Wilson al 95 %, que se porta bien con muestras pequeñas y con proporciones
cerca de 0 o de 1, donde el intervalo de libro (la proporción más o menos 1,96
errores típicos) da valores imposibles, por debajo de 0 o por encima de 1, o
un intervalo de anchura cero con 0 de 16.

Ejecutar desde la raíz, con los aciertos y el total de cada caso:

    python spikes/intervalo_wilson.py 1 16 0 16 98 104

Los aciertos pueden llevar decimales, para ver una tasa con otro tamaño de
muestra: «24.75 26» es la tasa de 99 de 104 con 26 casos.

Ojo: las repeticiones de una misma consulta no son independientes. «98 de 104»
son 26 consultas repetidas cuatro veces, y su intervalo honesto está entre el
de 104 casos y el de 26.
"""

import sys
from math import sqrt

# El cuantil de la normal que deja un 2,5 % en cada cola: el 95 %.
CUANTIL_95 = 1.959964


def wilson(aciertos: float, total: int, cuantil: float = CUANTIL_95) -> tuple[float, float]:
    """El intervalo de Wilson de `aciertos` de `total`, entre 0 y 1."""
    proporcion = aciertos / total
    denominador = 1 + cuantil**2 / total
    centro = (proporcion + cuantil**2 / (2 * total)) / denominador
    margen = (
        cuantil
        * sqrt(proporcion * (1 - proporcion) / total + cuantil**2 / (4 * total**2))
        / denominador
    )
    return max(0.0, centro - margen), min(1.0, centro + margen)


if __name__ == "__main__":
    argumentos = sys.argv[1:]
    if not argumentos or len(argumentos) % 2:
        sys.exit(__doc__)
    for posicion in range(0, len(argumentos), 2):
        aciertos, total = float(argumentos[posicion]), int(argumentos[posicion + 1])
        bajo, alto = wilson(aciertos, total)
        print(f"{argumentos[posicion]} de {total}: {bajo:.0%} – {alto:.0%}")
