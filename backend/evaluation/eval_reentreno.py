"""¿Qué rasgos y qué datos sacan al lineal del techo de Chakraborty? (#75, #78)

El lineal se entrenó sólo con Chakraborty, cuyas etiquetas son POR FUENTE
(BuzzFeed = clickbait, NYT = no), y sobre las pistas del léxico: la mitad de los
titulares sale con el vector vacío y recibe siempre la misma probabilidad, 0,163.
De ahí el techo de recall en Webis-17 (67,5 % en #109) y el F1 de 0,448 en
`validation170630` (#93), donde las dos clases comparten medio.

Este guion compara, con la regla escrita en #78 antes de medir, ocho
combinaciones: cuatro featurizaciones por dos conjuntos de entrenamiento.

- F0, las pistas del lineal de antes (`lineal_pistas.featurize_cues`), como
  referencia.
- F1, las palabras del titular en presencia/ausencia, más los cuatro patrones de
  estructura del léxico, que las palabras sueltas no ven.
- F2, lo mismo con TF-IDF.
- F3, F2 sin convenciones de tuit y con los números como `<number>`. Se añadió
  después de ver los pesos de F2, y así se declaró en #78 antes de medirla.

Con y sin `train170331` de Webis. Todas con la misma regresión logística:
desde #78, el algoritmo no es la palanca. Se eligen en los dos `dev` (el de
Chakraborty y `webis_dev`, el 20 % de `validation170630`).

La regla elegía F2, pero F2 y F3 empataron dentro del ruido (lo mide el
bootstrap de abajo), y el autor eligió F3 (`ELEGIDA`), que quita los rasgos de
época y de formato de tuit. Con `--test`, la elegida se mide UNA vez en los dos
`test` contra el lineal de antes, con la segunda parte de la regla. F3 pasó, y
desde entonces es la señal: su analizador es `linear.rasgos`, y el lineal de
antes vive congelado en `lineal_pistas`.

Con `--umbral`, la curva del lineal de producción en los dos `dev` y la regla
del umbral (el punto que dejó #93). Con `--ficha`, el acuerdo con el léxico que
cuenta su ficha.

LO QUE NO SE VE LEYENDO EL CÓDIGO

- Entrenar F0 sólo con Chakraborty reproduce el lineal de antes (mismos datos,
  mismo modelo): su fila tiene que coincidir con la de `lineal_pistas`, y es la
  comprobación de que el guion mide lo mismo que aquella señal.
- El «vector vacío» de F1 a F3 es un titular sin ninguna palabra del
  vocabulario aprendido ni ningún patrón: el equivalente del de F0.

Ejecutar:  python -m backend.evaluation.eval_reentreno [--test | --umbral | --ficha]
(antes, una vez: python -m backend.evaluation.splits webis)
"""

import random
import sys

from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    cohen_kappa_score,
    f1_score,
    precision_recall_fscore_support,
)

from backend.evaluation import lineal_pistas
from backend.evaluation.eval_external import load_external
from backend.evaluation.splits import load_split
from backend.integrations.nlp import lexical, linear

UMBRAL = 0.5
# La regla de #78, escrita antes de medir.
TOLERANCIA_CHAKRABORTY = 0.02
MEJORA_WEBIS = 0.05
F1_CHAKRABORTY_TEST_ANTES = 0.865  # el de la ficha del lineal de antes (#72, #76)

# Elegida por el autor ante el empate de F2 y F3 en `dev` (#78).
ELEGIDA = ("F3 tf-idf normalizado", "Chakraborty + Webis")
REMUESTREOS = 2000
SEMILLA = 24


def rasgos_de_palabras(titular: str) -> list[str]:
    """Las palabras del titular, en minúsculas, y sus patrones de estructura.

    Los patrones van con nombre propio (`<question>`), que no puede chocar con
    una palabra: el tokenizador no admite `<`. Se miran sobre el titular
    original, como hace el léxico, porque «mayúsculas» deja de existir al
    pasarlo a minúsculas.
    """
    palabras = lexical.TOKEN.findall(titular.lower())
    patrones = [
        f"<{nombre}>"
        for nombre, patron in lexical.PATTERNS.items()
        if patron.search(titular)
    ]
    return palabras + patrones


# F3 (#78) se añadió DESPUÉS de ver los pesos de F2, que traían vocabulario de
# fuente, época y formato de tuit (`2015`, `2008`, `rt`, `http`), y así se
# declaró en la issue antes de medirla. Su analizador es `linear.rasgos`: desde
# que ganó, la señal y este guion usan la misma función.


class Pistas:
    """F0 con la interfaz de un vectorizador de sklearn: el lineal de #109."""

    def fit_transform(self, titulares: list[str]) -> list[list[int]]:
        return self.transform(titulares)

    def transform(self, titulares: list[str]) -> list[list[int]]:
        return [lineal_pistas.featurize_cues(titular) for titular in titulares]


FEATURIZACIONES = {
    "F0 pistas": lambda: Pistas(),
    "F1 palabras": lambda: CountVectorizer(
        analyzer=rasgos_de_palabras, binary=True, min_df=2
    ),
    "F2 palabras tf-idf": lambda: TfidfVectorizer(
        analyzer=rasgos_de_palabras, min_df=2
    ),
    "F3 tf-idf normalizado": lambda: TfidfVectorizer(analyzer=linear.rasgos, min_df=2),
}


def _vacios(matriz) -> list[bool]:
    """Qué filas no tienen ningún rasgo: densas (F0) o dispersas (F1 a F3)."""
    if isinstance(matriz, list):
        return [not any(fila) for fila in matriz]
    return [cuenta == 0 for cuenta in matriz.getnnz(axis=1)]


def medir(predichas: list[int], etiquetas: list[int], vacios: list[bool]) -> dict:
    precision, recall, f1, _ = precision_recall_fscore_support(
        etiquetas, predichas, average="binary", zero_division=0
    )
    positivos = sum(etiquetas)
    invisibles = sum(
        1
        for vacio, etiqueta in zip(vacios, etiquetas, strict=True)
        if vacio and etiqueta
    )
    return {
        "p": precision,
        "r": recall,
        "f1": f1,
        "vacios": sum(vacios) / len(vacios),
        "techo": 1 - invisibles / positivos,
    }


def titulares_y_etiquetas(pares):
    return [titular for titular, _ in pares], [int(etiqueta) for _, etiqueta in pares]


def cargar_datos() -> dict:
    """Los cuatro conjuntos de la elección, y el entrenamiento de Webis limpio."""
    webis_dev = load_split("webis_dev")
    # `train170331` y `validation170630` son disjuntos salvo algún titular
    # (#121 midió uno): se quitan los que estén en la parte que elige o prueba.
    reservados = {titular for titular, _ in webis_dev + load_split("webis_test")}
    webis_completo = load_external("train170331")
    webis_train = [
        (titular, etiqueta)
        for titular, etiqueta, _ in webis_completo
        if titular not in reservados
    ]
    return {
        "chak_train": load_split("train"),
        "chak_dev": load_split("dev"),
        "webis_train": webis_train,
        "webis_dev": webis_dev,
        "quitados": len(webis_completo) - len(webis_train),
    }


def entrenar(featurizacion: str, pares: list[tuple[str, int]]):
    """Un vectorizador y una regresión logística, entrenados con `pares`."""
    titulares, etiquetas = titulares_y_etiquetas(pares)
    vectorizador = FEATURIZACIONES[featurizacion]()
    matriz = vectorizador.fit_transform(titulares)
    return vectorizador, LogisticRegression(max_iter=1000).fit(matriz, etiquetas)


def predecir(vectorizador, modelo, titulares: list[str]):
    matriz = vectorizador.transform(titulares)
    probabilidades = modelo.predict_proba(matriz)[:, 1]
    return [int(probabilidad >= UMBRAL) for probabilidad in probabilidades], matriz


def medir_antes(pares: list[tuple[str, int]]) -> tuple[dict, list[int]]:
    """El lineal de antes de #78, tal cual, por `lineal_pistas.predict`."""
    titulares, etiquetas = titulares_y_etiquetas(pares)
    predichas = [
        int(lineal_pistas.predict(titular).data["probability"] >= UMBRAL)
        for titular in titulares
    ]
    vacios = [not any(lineal_pistas.featurize_cues(titular)) for titular in titulares]
    return medir(predichas, etiquetas, vacios), predichas


def pesos_extremos(vectorizador, modelo, cuantos: int = 20) -> tuple[str, str]:
    """Los pesos que verá quien lea la tarjeta, para juzgar la explicación."""
    if isinstance(vectorizador, Pistas):
        nombres = list(lexical.PATTERNS) + lexical.ALL_CUES
    else:
        nombres = list(vectorizador.get_feature_names_out())
    pesos = sorted(
        zip(nombres, modelo.coef_[0], strict=True),
        key=lambda par: par[1],
        reverse=True,
    )
    formato = ", ".join
    return (
        formato(f"{nombre} {peso:.2f}" for nombre, peso in pesos[:cuantos]),
        formato(f"{nombre} {peso:.2f}" for nombre, peso in pesos[-cuantos:]),
    )


def diferencia_con_intervalo(
    etiquetas: list[int], unas: list[int], otras: list[int]
) -> tuple[float, float, float]:
    """F1(unas) − F1(otras), con su intervalo del 95 % por bootstrap emparejado:
    los mismos titulares remuestreados para las dos."""
    azar = random.Random(SEMILLA)
    diferencias = []
    for _ in range(REMUESTREOS):
        indices = [azar.randrange(len(etiquetas)) for _ in etiquetas]
        muestra = [etiquetas[indice] for indice in indices]
        diferencias.append(
            f1_score(muestra, [unas[indice] for indice in indices])
            - f1_score(muestra, [otras[indice] for indice in indices])
        )
    diferencias.sort()
    return (
        f1_score(etiquetas, unas) - f1_score(etiquetas, otras),
        diferencias[int(0.025 * REMUESTREOS)],
        diferencias[int(0.975 * REMUESTREOS) - 1],
    )


def comparar_en_dev() -> None:
    datos = cargar_datos()
    cruce = {titular for titular, _ in datos["chak_train"]} & {
        titular for titular, _ in datos["webis_train"]
    }
    print("== datos")
    print(
        f"  Chakraborty train {len(datos['chak_train'])} · dev {len(datos['chak_dev'])}"
    )
    print(
        f"  Webis train170331 {len(datos['webis_train'])} (quitados {datos['quitados']} "
        f"que están en validation170630) · webis_dev {len(datos['webis_dev'])}"
    )
    print(f"  titulares a la vez en Chakraborty train y Webis train: {len(cruce)}")

    devs = {"Chakraborty dev": datos["chak_dev"], "Webis dev": datos["webis_dev"]}
    antes = {nombre: medir_antes(pares)[0] for nombre, pares in devs.items()}
    filas = [("lineal de antes", "—", len(lineal_pistas.pesos()["weights"]), antes)]
    modelos = {}
    predicciones_webis = {}
    for conjunto, entrenamiento in (
        ("Chakraborty", datos["chak_train"]),
        ("Chakraborty + Webis", datos["chak_train"] + datos["webis_train"]),
    ):
        for featurizacion in FEATURIZACIONES:
            vectorizador, modelo = entrenar(featurizacion, entrenamiento)
            numero_de_rasgos = (
                len(lexical.PATTERNS) + len(lexical.ALL_CUES)
                if isinstance(vectorizador, Pistas)
                else len(vectorizador.vocabulary_)
            )
            resultados = {}
            for nombre, pares in devs.items():
                titulares, etiquetas = titulares_y_etiquetas(pares)
                predichas, matriz = predecir(vectorizador, modelo, titulares)
                resultados[nombre] = medir(predichas, etiquetas, _vacios(matriz))
                if nombre == "Webis dev":
                    predicciones_webis[(featurizacion, conjunto)] = predichas
            filas.append((featurizacion, conjunto, numero_de_rasgos, resultados))
            modelos[(featurizacion, conjunto)] = (vectorizador, modelo)

    print("\n== en los dos dev, umbral 0,5")
    print(
        "  featurización          datos                 rasgos  "
        "F1 Chak   F1 Webis  P Webis  R Webis  vacíos Webis  techo R Webis"
    )
    for featurizacion, conjunto, numero_de_rasgos, resultados in filas:
        chak, webis = resultados["Chakraborty dev"], resultados["Webis dev"]
        print(
            f"  {featurizacion:22s} {conjunto:21s} {numero_de_rasgos:6d}  "
            f"{chak['f1']:.3f}     {webis['f1']:.3f}     {webis['p']:.3f}    "
            f"{webis['r']:.3f}    {webis['vacios']:6.1%}        {webis['techo']:.1%}"
        )

    # La regla de #78, paso 1.
    suelo = antes["Chakraborty dev"]["f1"] - TOLERANCIA_CHAKRABORTY
    candidatas = [
        fila for fila in filas[1:] if fila[3]["Chakraborty dev"]["f1"] >= suelo
    ]
    print(
        f"\n== la regla: F1 Chakraborty dev ≥ {suelo:.3f}; gana el mejor F1 en Webis dev"
    )
    if not candidatas:
        print("  ninguna combinación la cumple: se queda el lineal de antes")
        return
    ganadora = max(candidatas, key=lambda fila: fila[3]["Webis dev"]["f1"])
    print(f"  gana: {ganadora[0]} con {ganadora[1]}")

    # El empate que llevó a elegir F3 (#78).
    _, etiquetas_webis = titulares_y_etiquetas(datos["webis_dev"])
    if (ganadora[0], ganadora[1]) != ELEGIDA:
        diferencia, bajo, alto = diferencia_con_intervalo(
            etiquetas_webis,
            predicciones_webis[(ganadora[0], ganadora[1])],
            predicciones_webis[ELEGIDA],
        )
        distintas = sum(
            1
            for una, otra in zip(
                predicciones_webis[(ganadora[0], ganadora[1])],
                predicciones_webis[ELEGIDA],
                strict=True,
            )
            if una != otra
        )
        print(
            f"  F1 Webis dev de la ganadora − la elegida ({ELEGIDA[0]}): "
            f"{diferencia:+.4f}, intervalo del 95 % [{bajo:+.4f}, {alto:+.4f}] "
            f"({REMUESTREOS} remuestreos); discrepan en {distintas} de "
            f"{len(etiquetas_webis)}"
        )

    for clave in dict.fromkeys(((ganadora[0], ganadora[1]), ELEGIDA)):
        a_favor, en_contra = pesos_extremos(*modelos[clave])
        print(f"\n  {clave[0]} con {clave[1]}")
        print(f"    a favor de clickbait: {a_favor}")
        print(f"    en contra: {en_contra}")


def prueba_final() -> None:
    """La segunda parte de la regla de #78, sobre los dos `test`. Una sola vez."""
    datos = cargar_datos()
    vectorizador, modelo = entrenar(
        ELEGIDA[0], datos["chak_train"] + datos["webis_train"]
    )
    tests = {
        "Chakraborty test": load_split("test"),
        "Webis test": load_split("webis_test"),
    }
    print(f"== {ELEGIDA[0]} con {ELEGIDA[1]}, contra el lineal de antes, umbral 0,5")
    resultados = {}
    for nombre, pares in tests.items():
        titulares, etiquetas = titulares_y_etiquetas(pares)
        antes, _ = medir_antes(pares)
        predichas, matriz = predecir(vectorizador, modelo, titulares)
        nuevo = medir(predichas, etiquetas, _vacios(matriz))
        resultados[nombre] = (antes, nuevo)
        print(f"  {nombre} ({len(pares)}, {sum(etiquetas)} clickbait)")
        for etiqueta, medida in (("antes", antes), ("elegida", nuevo)):
            print(
                f"    {etiqueta:8s} P {medida['p']:.3f} · R {medida['r']:.3f} · "
                f"F1 {medida['f1']:.3f} · vacíos {medida['vacios']:.1%} · "
                f"techo de recall {medida['techo']:.1%}"
            )

    antes_webis, nuevo_webis = resultados["Webis test"]
    _, nuevo_chak = resultados["Chakraborty test"]
    sube_webis = nuevo_webis["f1"] - antes_webis["f1"]
    suelo_chak = F1_CHAKRABORTY_TEST_ANTES - TOLERANCIA_CHAKRABORTY
    print("\n== la regla, paso 2")
    print(
        f"  Webis: F1 sube {sube_webis:+.3f} (hace falta +{MEJORA_WEBIS:.2f}) → "
        f"{'cumple' if sube_webis >= MEJORA_WEBIS else 'NO cumple'}"
    )
    print(
        f"  Chakraborty: F1 {nuevo_chak['f1']:.3f} (suelo {suelo_chak:.3f}) → "
        f"{'cumple' if nuevo_chak['f1'] >= suelo_chak else 'NO cumple'}"
    )
    queda = sube_webis >= MEJORA_WEBIS and nuevo_chak["f1"] >= suelo_chak
    print(f"  => {'SE QUEDA' if queda else 'se queda el lineal de antes'}")


# El umbral del lineal nuevo (el punto que dejó #93 en #78), con la regla de #78.
UMBRALES = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)
MEJORA_MINIMA_DEL_UMBRAL = 0.01


def elegir_umbral() -> None:
    """La curva del lineal de producción en los dos `dev`, y la regla del umbral:
    se queda en 0,5 salvo que otro corte suba el F1 medio de los dos dominios al
    menos `MEJORA_MINIMA_DEL_UMBRAL`."""
    datos = cargar_datos()
    devs = {"Chakraborty dev": datos["chak_dev"], "Webis dev": datos["webis_dev"]}
    probabilidades = {
        nombre: [linear.predict(titular).data["probability"] for titular, _ in pares]
        for nombre, pares in devs.items()
    }
    print("== el lineal de producción en los dos dev")
    print("  umbral   F1 Chak   F1 Webis   F1 medio")
    medios = {}
    for umbral in UMBRALES:
        f1s = []
        for nombre, pares in devs.items():
            _, etiquetas = titulares_y_etiquetas(pares)
            predichas = [
                int(probabilidad >= umbral) for probabilidad in probabilidades[nombre]
            ]
            f1s.append(f1_score(etiquetas, predichas))
        medios[umbral] = sum(f1s) / len(f1s)
        print(
            f"  {umbral:.2f}     {f1s[0]:.3f}     {f1s[1]:.3f}      {medios[umbral]:.3f}"
        )
    mejor = max(medios, key=lambda umbral: medios[umbral])
    gana = medios[mejor] - medios[UMBRAL] >= MEJORA_MINIMA_DEL_UMBRAL
    print(
        f"\n  mejor corte {mejor:.2f} ({medios[mejor]:.3f}) frente a 0,50 "
        f"({medios[UMBRAL]:.3f}): {'SE CAMBIA' if gana else 'se queda 0,5'}"
    )


def cifras_de_la_ficha() -> None:
    """Lo que la ficha del lineal dice y no sale de `--test`: el acuerdo con el
    léxico, que hasta #78 era por construcción (#109)."""
    datos = cargar_datos()
    print("== acuerdo con el léxico (umbral 1), en los dos dev")
    for nombre, pares in (
        ("Chakraborty dev", datos["chak_dev"]),
        ("Webis dev", datos["webis_dev"]),
    ):
        titulares, _ = titulares_y_etiquetas(pares)
        lexico = [
            int(lexical.detect(titular).data["is_clickbait"]) for titular in titulares
        ]
        for etiqueta, modulo in (("antes", lineal_pistas), ("ahora", linear)):
            votos = [
                int(modulo.predict(titular).data["is_clickbait"])
                for titular in titulares
            ]
            acuerdo = sum(
                1 for uno, otro in zip(lexico, votos, strict=True) if uno == otro
            )
            print(
                f"  {nombre:16s} {etiqueta}: acuerdo {acuerdo / len(titulares):.1%} · "
                f"kappa {cohen_kappa_score(lexico, votos):.3f}"
            )


if __name__ == "__main__":
    if "--test" in sys.argv:
        prueba_final()
    elif "--umbral" in sys.argv:
        elegir_umbral()
    elif "--ficha" in sys.argv:
        cifras_de_la_ficha()
    else:
        comparar_en_dev()
