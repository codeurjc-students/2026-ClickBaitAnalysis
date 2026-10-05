"""¿Merece la pena calibrar el umbral del lineal, como el de la incoherencia? (#93)

``linear.predict`` declara clickbait con ``probabilidad >= 0.5``. Al hacer
configurables los umbrales de los detectores (#93) salió la pregunta de si ese
0,5 debía calibrarse con el método de #92 (``eval_incoherencia``): elegir el
corte en unos datos y comprobarlo en otros. Este guion responde a la pregunta
previa, **¿mover el corte cambia algo?**, recorriendo la curva en los dos
dominios.

LO QUE NO SE VE LEYENDO EL CÓDIGO

Un titular en el que el léxico no encuentra ninguna pista tiene el vector vacío:
``w·x = 0`` y la probabilidad es ``sigmoid(intercepto)``, LA MISMA para todos.
El umbral no puede separar esos titulares entre sí: si queda por debajo de ese
valor los marca todos, y si queda por encima, ninguno. Sólo reordena los que
tienen alguna pista. Por eso el guion cuenta cuántos titulares salen con el
vector vacío y cuántos clickbait hay entre ellos: es el techo de recall que
ningún umbral levanta, y lo que ataca #75 (ver la ficha).

LOS DATOS

- ``dev`` de Chakraborty (#72), que es el split para afinar umbrales. El
  ``test`` no se toca: está congelado.
- ``validation170630`` de Webis-17, el grande (19.484). Las cifras de Webis de la
  ficha salieron del pequeño (``train170331``, #76), así que no coinciden con
  éstas.

Los pesos son los de ``linear_clickbait.json``: si #75 o #78 reentrenan el
modelo, la curva se vuelve a sacar.

Ejecutar:  python -m backend.evaluation.eval_umbral_lineal
"""

import math

from backend.evaluation.eval_external import load_external
from backend.evaluation.splits import load_split
from backend.integrations.nlp import linear

UMBRALES = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80)
SPLIT_WEBIS = "validation170630"


def probabilidad_sin_pistas() -> float:
    """La probabilidad que da el modelo a un titular con el vector vacío."""
    return 1 / (1 + math.exp(-linear.pesos()["intercept"]))


def curva(nombre: str, pares: list[tuple[str, int]]) -> None:
    """Precisión, recall y F1 del lineal en cada umbral, con el techo de recall
    que deja el vector vacío."""
    p_vacio = probabilidad_sin_pistas()
    probabilidades = [
        linear.predict(titular).data["probability"] for titular, _ in pares
    ]
    etiquetas = [etiqueta for _, etiqueta in pares]
    positivos = sum(etiquetas)

    vacios = [abs(probabilidad - p_vacio) < 1e-12 for probabilidad in probabilidades]
    clickbait_vacios = sum(
        1
        for vacio, etiqueta in zip(vacios, etiquetas, strict=True)
        if vacio and etiqueta
    )

    print(
        f"\n== {nombre}: {len(pares)} titulares, {positivos} clickbait "
        f"({positivos / len(pares):.1%})"
    )
    print(
        f"   vector vacío: {sum(vacios)} ({sum(vacios) / len(pares):.1%}); "
        f"clickbait entre ellos: {clickbait_vacios} -> techo de recall "
        f"{1 - clickbait_vacios / positivos:.1%}"
    )
    print("   umbral  precisión  recall  F1     marcados")
    for umbral in UMBRALES:
        marcados = [probabilidad >= umbral for probabilidad in probabilidades]
        aciertos = sum(
            1
            for marcado, etiqueta in zip(marcados, etiquetas, strict=True)
            if marcado and etiqueta
        )
        precision = aciertos / sum(marcados) if any(marcados) else 0.0
        recall = aciertos / positivos
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        print(
            f"   {umbral:.2f}    {precision:.3f}      {recall:.3f}   {f1:.3f}  "
            f"{sum(marcados) / len(pares):.1%}"
        )


if __name__ == "__main__":
    intercepto = linear.pesos()["intercept"]
    print(
        f"intercepto {intercepto:.3f} -> probabilidad con el vector vacío "
        f"{probabilidad_sin_pistas():.3f}"
    )
    curva("Chakraborty dev", load_split("dev"))
    curva(
        f"Webis-17 {SPLIT_WEBIS}",
        [(titular, etiqueta) for titular, etiqueta, _ in load_external(SPLIT_WEBIS)],
    )
