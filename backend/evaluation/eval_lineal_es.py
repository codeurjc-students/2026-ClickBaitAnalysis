"""¿Un lineal para el español, o uno para los dos idiomas? (issue #231)

El lineal (#78) se entrenó con titulares en inglés, y en TA1C `validation`, con
el español tratado como inglés, daba F1 0,019 (#229): casi ninguna de sus
palabras aparece en un tuit en español. Este guion compara dos maneras de
darle pesos en español, las dos con F3 (`linear.rasgos` con TF-IDF, `min_df=2`)
y la misma regresión logística de #78:

- por idioma: sólo el `train` de TA1C (2.100 tuits);
- bilingüe: el `train` de Chakraborty, `train170331` de Webis-17 y el de TA1C.

Se miden en los tres `dev` —Chakraborty `dev`, `webis_dev` y TA1C
`validation`— con la regla publicada en la issue antes de medir: gana el
bilingüe, salvo que el de por idioma le gane en TA1C `validation` por más del
ruido, o que el bilingüe baje más de 0,01 alguno de los `dev` ingleses respecto
al lineal de producción.

LAS TRES PARTES

    .venv/bin/python -m backend.evaluation.eval_lineal_es           # los tres dev y la regla
    .venv/bin/python -m backend.evaluation.eval_lineal_es --umbral  # el umbral de la elegida
    .venv/bin/python -m backend.evaluation.eval_lineal_es --test    # una sola vez

`--umbral` y `--test` usan `ELEGIDA` y `UMBRAL_DE_LA_ELEGIDA`, que se fijan aquí
a mano al ver el resultado de la anterior, como el `ELEGIDA` de #78: así lo que
se prueba queda escrito, y `--test` no corre sin ello. `test` se abre UNA vez.
Si la elegida es el bilingüe, cambia también el inglés, y se mide además en
los dos `test` ingleses: para `webis_test` es su segunda apertura (la primera
fue la de #78), declarada en la regla.
"""

import sys

from sklearn.metrics import f1_score

from backend.evaluation.eval_reentreno import (
    MEJORA_MINIMA_DEL_UMBRAL,
    REMUESTREOS,
    UMBRAL,
    UMBRALES,
    _vacios,
    cargar_datos,
    diferencia_con_intervalo,
    entrenar,
    medir,
    pesos_extremos,
    predecir,
    titulares_y_etiquetas,
)
from backend.evaluation.splits import load_split
from backend.integrations.nlp import lexical, linear

FEATURIZACION = "F3 tf-idf normalizado"  # la de #78: `linear.rasgos`
POR_IDIOMA = "por idioma"
BILINGUE = "bilingüe"

# La regla (comentario en #231), escrita antes de medir.
TOLERANCIA_INGLES_DEV = 0.01
BASE_TA1C = 0.61  # TF-IDF + XGBoost, la base publicada en el `test` de TA1C
TOLERANCIA_INGLES_TEST = 0.02
F1_TEST_DE_78 = {"Chakraborty test": 0.961, "Webis test": 0.534}

# Se fijan a mano al ver la parte anterior (ver el docstring).
ELEGIDA: str | None = None
UMBRAL_DE_LA_ELEGIDA = UMBRAL

DEVS = {
    "Chakraborty dev": "chak_dev",
    "Webis dev": "webis_dev",
    "TA1C validation": "ta1c_validation",
}
INGLESES = ("Chakraborty dev", "Webis dev")


def cargar() -> dict:
    """Los conjuntos de #78 y los de TA1C."""
    datos = cargar_datos()
    for parte in ("ta1c_train", "ta1c_validation"):
        datos[parte] = load_split(parte)
    return datos


def entrenamiento(candidato: str, datos: dict) -> list[tuple[str, int]]:
    if candidato == POR_IDIOMA:
        return datos["ta1c_train"]
    return datos["chak_train"] + datos["webis_train"] + datos["ta1c_train"]


def produccion(pares: list[tuple[str, int]]) -> tuple[dict, list[int]]:
    """El lineal de producción (inglés), tal cual, por `linear.predict`."""
    titulares, etiquetas = titulares_y_etiquetas(pares)
    predichas = [
        int(linear.predict(titular).data["is_clickbait"]) for titular in titulares
    ]
    vacios = [not linear.vectorizar(titular) for titular in titulares]
    return medir(predichas, etiquetas, vacios), predichas


def _patrones(vectorizador, modelo) -> str:
    """El peso de los cuatro patrones de estructura, que se leen aparte."""
    pesos = dict(
        zip(vectorizador.get_feature_names_out(), modelo.coef_[0], strict=True)
    )
    return ", ".join(
        f"<{nombre}> {pesos[f'<{nombre}>']:+.2f}"
        for nombre in lexical.PATTERNS
        if f"<{nombre}>" in pesos
    )


def comparar_en_dev() -> None:
    datos = cargar()
    print("== datos")
    for parte in ("chak_train", "webis_train", "ta1c_train", *DEVS.values()):
        pares = datos[parte]
        clickbait = sum(etiqueta for _, etiqueta in pares)
        print(
            f"  {parte:16s} {len(pares):6d} titulares, {clickbait / len(pares):5.1%} clickbait"
        )
    repetidos = {titular for titular, _ in datos["ta1c_train"]} & {
        titular for titular, _ in datos["ta1c_validation"]
    }
    print(f"  tuits a la vez en el train y en validation de TA1C: {len(repetidos)}")

    resultados: dict[str, dict] = {}
    predicciones: dict[str, dict] = {}
    modelos = {}
    for candidato in (POR_IDIOMA, BILINGUE):
        vectorizador, modelo = entrenar(FEATURIZACION, entrenamiento(candidato, datos))
        modelos[candidato] = (vectorizador, modelo)
        resultados[candidato], predicciones[candidato] = {}, {}
        for nombre, parte in DEVS.items():
            titulares, etiquetas = titulares_y_etiquetas(datos[parte])
            predichas, matriz = predecir(vectorizador, modelo, titulares)
            resultados[candidato][nombre] = medir(predichas, etiquetas, _vacios(matriz))
            predicciones[candidato][nombre] = predichas
    resultados["producción"], predicciones["producción"] = {}, {}
    for nombre in INGLESES:
        medida, predichas = produccion(datos[DEVS[nombre]])
        resultados["producción"][nombre] = medida
        predicciones["producción"][nombre] = predichas

    print("\n== en los tres dev, umbral 0,5")
    print(
        "  candidato     rasgos   F1 Chak   F1 Webis   F1 TA1C   P TA1C   R TA1C   vacíos TA1C"
    )
    for candidato, medidas in resultados.items():
        rasgos = (
            len(modelos[candidato][0].vocabulary_)
            if candidato in modelos
            else len(linear.pesos()["weights"])
        )
        ta1c = medidas.get("TA1C validation")
        print(
            f"  {candidato:12s} {rasgos:6d}    {medidas['Chakraborty dev']['f1']:.3f}     "
            f"{medidas['Webis dev']['f1']:.3f}      "
            + (
                f"{ta1c['f1']:.3f}     {ta1c['p']:.3f}    {ta1c['r']:.3f}    {ta1c['vacios']:6.1%}"
                if ta1c
                else "  —   (el de producción no analiza español)"
            )
        )

    print("\n== la regla (comentario en #231)")
    _, etiquetas_ta1c = titulares_y_etiquetas(datos["ta1c_validation"])
    diferencia, bajo, alto = diferencia_con_intervalo(
        etiquetas_ta1c,
        predicciones[POR_IDIOMA]["TA1C validation"],
        predicciones[BILINGUE]["TA1C validation"],
    )
    gana_por_idioma = bajo > 0
    print(
        f"  TA1C validation, por idioma − bilingüe: {diferencia:+.4f}, intervalo del 95 % "
        f"[{bajo:+.4f}, {alto:+.4f}] ({REMUESTREOS} remuestreos) → "
        + (
            "el de por idioma gana por más del ruido"
            if gana_por_idioma
            else "no gana por más del ruido"
        )
    )
    baja_ingles = False
    for nombre in INGLESES:
        cambio = (
            resultados[BILINGUE][nombre]["f1"] - resultados["producción"][nombre]["f1"]
        )
        baja = cambio < -TOLERANCIA_INGLES_DEV
        baja_ingles = baja_ingles or baja
        _, etiquetas = titulares_y_etiquetas(datos[DEVS[nombre]])
        _, bajo_ingles, alto_ingles = diferencia_con_intervalo(
            etiquetas,
            predicciones[BILINGUE][nombre],
            predicciones["producción"][nombre],
        )
        print(
            f"  {nombre}, bilingüe − producción: {cambio:+.4f} "
            f"[{bajo_ingles:+.4f}, {alto_ingles:+.4f}] → "
            + (
                f"BAJA más de {TOLERANCIA_INGLES_DEV}"
                if baja
                else f"no baja más de {TOLERANCIA_INGLES_DEV}"
            )
        )
    elegida = POR_IDIOMA if gana_por_idioma or baja_ingles else BILINGUE
    print(f"  => la regla elige: {elegida.upper()}")

    for candidato, (vectorizador, modelo) in modelos.items():
        a_favor, en_contra = pesos_extremos(vectorizador, modelo)
        print(f"\n  {candidato}")
        print(f"    a favor de clickbait: {a_favor}")
        print(f"    en contra: {en_contra}")
        print(f"    patrones: {_patrones(vectorizador, modelo)}")

    print(
        f"\n  (Para `--umbral` y `--test`, fija ELEGIDA = {'POR_IDIOMA' if elegida == POR_IDIOMA else 'BILINGUE'} en el guion.)"
    )


def _la_elegida() -> str:
    if ELEGIDA is None:
        raise SystemExit(
            "Fija antes ELEGIDA en el guion, con el resultado de la comparación en dev."
        )
    return ELEGIDA


def elegir_umbral() -> None:
    """La regla del umbral de #78, sobre la elegida: se queda 0,5 salvo que otro
    corte suba el F1 al menos 0,01 (el de TA1C si es por idioma; la media de los
    tres `dev` si es bilingüe)."""
    elegida = _la_elegida()
    datos = cargar()
    vectorizador, modelo = entrenar(FEATURIZACION, entrenamiento(elegida, datos))
    devs = {"TA1C validation": "ta1c_validation"} if elegida == POR_IDIOMA else DEVS
    probabilidades = {}
    for nombre, parte in devs.items():
        titulares, _ = titulares_y_etiquetas(datos[parte])
        probabilidades[nombre] = modelo.predict_proba(
            vectorizador.transform(titulares)
        )[:, 1]

    print(f"== {elegida}: F1 por umbral")
    print("  umbral   " + "   ".join(f"{nombre:16s}" for nombre in devs) + "   media")
    medias = {}
    for umbral in UMBRALES:
        f1s = []
        for nombre, parte in devs.items():
            _, etiquetas = titulares_y_etiquetas(datos[parte])
            f1s.append(
                f1_score(
                    etiquetas,
                    [
                        int(probabilidad >= umbral)
                        for probabilidad in probabilidades[nombre]
                    ],
                )
            )
        medias[umbral] = sum(f1s) / len(f1s)
        print(
            f"  {umbral:.2f}     "
            + "   ".join(f"{f1:16.3f}" for f1 in f1s)
            + f"   {medias[umbral]:.3f}"
        )
    mejor = max(medias, key=lambda umbral: medias[umbral])
    cambia = medias[mejor] - medias[UMBRAL] >= MEJORA_MINIMA_DEL_UMBRAL
    print(
        f"\n  mejor corte {mejor:.2f} ({medias[mejor]:.3f}) frente a 0,50 ({medias[UMBRAL]:.3f}): "
        + (
            f"SE CAMBIA (fija UMBRAL_DE_LA_ELEGIDA = {mejor})"
            if cambia
            else "se queda 0,5"
        )
    )


def prueba_final() -> None:
    """La elegida, UNA vez, en el `test` de TA1C y, si es bilingüe, en los
    ingleses, con la regla de cuándo se queda."""
    elegida = _la_elegida()
    datos = cargar()
    vectorizador, modelo = entrenar(FEATURIZACION, entrenamiento(elegida, datos))
    tests = {"TA1C test": "ta1c_test"}
    if elegida == BILINGUE:
        tests |= {"Chakraborty test": "test", "Webis test": "webis_test"}

    print(f"== {elegida}, umbral {UMBRAL_DE_LA_ELEGIDA:.2f}, en test (una sola vez)")
    queda = True
    for nombre, parte in tests.items():
        pares = load_split(parte)
        titulares, etiquetas = titulares_y_etiquetas(pares)
        matriz = vectorizador.transform(titulares)
        predichas = [
            int(probabilidad >= UMBRAL_DE_LA_ELEGIDA)
            for probabilidad in modelo.predict_proba(matriz)[:, 1]
        ]
        medida = medir(predichas, etiquetas, _vacios(matriz))
        suelo = (
            BASE_TA1C
            if nombre == "TA1C test"
            else F1_TEST_DE_78[nombre] - TOLERANCIA_INGLES_TEST
        )
        cumple = medida["f1"] >= suelo
        queda = queda and cumple
        print(
            f"  {nombre:16s} ({len(pares)}, {sum(etiquetas)} clickbait): P {medida['p']:.3f} · "
            f"R {medida['r']:.3f} · F1 {medida['f1']:.3f} · vacíos {medida['vacios']:.1%} "
            f"→ suelo {suelo:.3f}: {'cumple' if cumple else 'NO cumple'}"
        )
    print(f"  => {'SE QUEDA' if queda else 'NO se queda'}")


if __name__ == "__main__":
    if "--test" in sys.argv:
        prueba_final()
    elif "--umbral" in sys.argv:
        elegir_umbral()
    else:
        comparar_en_dev()
