"""#256 (2026-11-07) - ¿Por qué los patrones del lineal pesan como pesan?

El lineal usa cuatro patrones de estructura: número inicial, interrogación,
mayúsculas y puntos suspensivos. Tres de ellos parecen pistas de clickbait, y
aun así, en el bilingüe, las mayúsculas y la elipsis restan (−1,60 y −0,87) y la
interrogación casi no pesa (+0,43). #78 dio tres hipótesis sin medirlas:

1. las palabras interrogativas (`why`, `how`) ya llevan el peso de la pregunta;
2. en los tuits de Webis-17, los puntos suspensivos son de recorte;
3. las mayúsculas son de «BREAKING».

Y la salida de `eval_lineal_es` daba una pista: el signo cambia según con qué
corpus se entrene. Este guion lo mira en cuatro partes:

- `recuento`: cuánto clickbait hay con cada patrón y sin él, por corpus, sin
  ningún modelo. Es lo que el patrón puede aprender de cada uno.
- `hipotesis`: las tres de arriba, contadas en los `train`.
- `pesos_por_corpus`: la receta de producción con cada corpus solo, con dos y con
  los tres. Y los tres sin las palabras interrogativas, que es la hipótesis 1
  dentro del modelo: si esas palabras se llevan el peso, sin ellas la interrogación
  tiene que subir.
- `sin_patron`: quita cada patrón del bilingüe y mide en los tres `dev`, con el
  umbral de producción. Un peso no dice cuánto aporta un rasgo: lo dice quitarlo.

QUÉ NO ES

- **No cambia el lineal.** Sólo describe. Si quitar un patrón mejorara algo, no
  se aplicaría: pediría reentrenar y abrir otra vez `test`, que es otra decisión.
- **No toca `test`.** Las etiquetas salen de los `train` y los `dev`.
  `cargar_datos` lee los titulares de `webis_test` sólo para quitar del
  entrenamiento el tuit repetido, como desde #78.
- **Son asociaciones, no causas.** Un peso depende de los demás rasgos, y un
  recuento en un corpus dice cómo es ese corpus, no el clickbait en general.

Comprueba antes de leer nada que reproduce lo publicado: los pesos de #78 y #231,
los de `eval_lineal_es` y el F1 del bilingüe en los tres `dev`. Si no, aborta.

Ejecutar desde la raíz, en CPU (unos 3 min). No escribe ningún fichero:

    .venv/bin/python spikes/lineal_patrones.py

Resultados (2026-11-07, sobre `9335657`, en el PC, con scikit-learn 1.9.0). Los
dos controles reproducen lo publicado.

| `train` | Patrón | Titulares | Clickbait con él | Sin él | Peso, sólo ese corpus |
|---|---|---|---|---|---|
| Chakraborty | número inicial | 3.837 | 93,7 % | 39,1 % | +11,71 |
| Webis-17 | número inicial | 86 | 70,9 % | 29,6 % | +2,99 |
| TA1C | número inicial | 18 | 66,7 % | 27,8 % | +1,18 |
| Chakraborty | interrogación | 48 | 0,0 % | 50,1 % | −3,79 |
| Webis-17 | interrogación | 71 | 71,8 % | 29,8 % | +2,27 |
| TA1C | interrogación | 48 | 95,8 % | 26,6 % | +3,71 |
| Chakraborty | mayúsculas | 312 | 27,2 % | 50,4 % | −0,49 |
| Webis-17 | mayúsculas | 281 | 20,6 % | 32,3 % | −0,91 |
| TA1C | mayúsculas | 207 | 17,4 % | 29,3 % | −0,83 |
| Chakraborty | elipsis | 9 | 77,8 % | 50,0 % | +0,12 |
| Webis-17 | elipsis | 33 | 21,2 % | 31,1 % | −0,63 |
| TA1C | elipsis | 39 | 41,0 % | 27,9 % | +0,69 |

Juntos: los tres corpus, +12,49, +0,43, −1,60 y −0,87 (número, interrogación,
mayúsculas y elipsis); sin las palabras interrogativas, +12,45, +1,29, −1,63 y
−0,92; Chakraborty y Webis-17, +12,12, −1,59, −1,49 y −1,51.

Lo que dicen, y es una lectura:

- **La interrogación no pesa porque los corpus se contradicen.** Con `?` final
  hay un 71,8 % y un 95,8 % de clickbait en Webis-17 y TA1C, y un 0,0 % en
  Chakraborty: ninguno de sus 9.599 clickbait de `train` acaba en `?`, y de los
  1.179 que empiezan por palabra interrogativa («How Well Do You Remember 2015»,
  «What Does Your Choice Of Spiral Say About You») tampoco. Parece un artefacto
  del corpus, sin comprobar en su origen.
- **La hipótesis 1 explica poco**: sin las palabras interrogativas el peso sube de
  +0,43 a +1,29, y con `?` final hay el mismo clickbait con ellas y sin ellas
  (74,2 y 70,0 % en Webis-17; 96,9 y 93,8 % en TA1C).
- **La hipótesis 2 no se sostiene**: en Webis-17 la elipsis está al final en 16 de
  33 tuits, y resta en los dos sitios (25,0 y 17,6 %, con un 31,0 % de base). Son
  muy pocos casos: 81 de 23.758 en el entrenamiento.
- **La hipótesis 3 tampoco**: «BREAKING» son 12 de 315 apariciones en Webis-17. Lo
  que dispara las mayúsculas son siglas: NASA, NATO y FIFA; VIDEO, ISIS y WATCH;
  COVID, ATENCIÓN y EEUU. Es el único patrón que resta en los tres corpus: las
  siglas son de noticias.
- **Un peso no dice cuánto aporta.** Quitar la interrogación, las mayúsculas o la
  elipsis no mueve el F1 de ningún `dev` por encima del ruido. Sólo el número
  inicial aporta en tuits: sin él, `webis_dev` baja 0,0102 [−0,0174, −0,0030] y
  TA1C `validation` 0,0348 [−0,0701, −0,0003]; en Chakraborty `dev` no cambia.
  Sin mayúsculas, TA1C `validation` sube 0,0072 [+0,0000, +0,0173], en el filo.
- **Sin explicar**: juntos, la elipsis pesa −1,51 con Chakraborty y Webis-17, más
  que cualquiera de los dos solos (+0,12 y −0,63). Un peso depende de los demás
  rasgos, y el recuento no lo explica todo.
"""

import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import f1_score  # noqa: E402

from backend.evaluation.eval_lineal_es import cargar  # noqa: E402
from backend.evaluation.eval_reentreno import (  # noqa: E402
    diferencia_con_intervalo,
    titulares_y_etiquetas,
)
from backend.integrations.nlp import lexical, linear  # noqa: E402

UMBRAL = 0.35  # el de producción desde #231
PATRONES = tuple(f"<{nombre}>" for nombre in lexical.PATTERNS)

ENTRENAMIENTOS = {
    "Chakraborty": "chak_train",
    "Webis-17": "webis_train",
    "TA1C": "ta1c_train",
}
DEVS = {
    "Chakraborty dev": "chak_dev",
    "webis_dev": "webis_dev",
    "TA1C validation": "ta1c_validation",
}

# Con tilde en español: sin ella, «que» y «como» son otra palabra.
INTERROGATIVAS = frozenset(
    {
        "what",
        "why",
        "how",
        "who",
        "which",
        "when",
        "where",
        "qué",
        "cómo",
        "cuál",
        "cuáles",
        "quién",
        "quiénes",
        "cuándo",
        "dónde",
        "cuánto",
        "cuánta",
        "cuántos",
        "cuántas",
    }
)

ELIPSIS_AL_FINAL = re.compile(r"(?:\.\.\.|…)\s*$")

# Lo publicado, para comprobar que este guion mide lo mismo.
TOLERANCIA = 0.006
PESOS_PUBLICADOS = {
    "Chakraborty + Webis-17": {  # #78
        "<leading_number>": 12.12,
        "<question>": -1.59,
        "<all_caps>": -1.49,
        "<ellipsis>": -1.51,
    },
    "TA1C": {  # `eval_lineal_es`
        "<leading_number>": 1.18,
        "<question>": 3.71,
        "<all_caps>": -0.83,
        "<ellipsis>": 0.69,
    },
    "los tres": {  # #231
        "<leading_number>": 12.49,
        "<question>": 0.43,
        "<all_caps>": -1.60,
        "<ellipsis>": -0.87,
    },
}
F1_PUBLICADO = {"Chakraborty dev": 0.962, "webis_dev": 0.535, "TA1C validation": 0.609}


def _limpio(titular: str) -> str:
    """El titular sin enlaces, menciones ni `RT`, como lo ve `linear.rasgos`."""
    return linear.RETUIT.sub(
        " ", linear.MENCION.sub(" ", linear.ENLACE.sub(" ", titular))
    )


def _porcentaje(parte: int, total: int) -> str:
    return f"{100 * parte / total:5.1f} %" if total else "    —  "


def _clickbait(pares: list[tuple[str, int]]) -> str:
    """Cuántos hay y cuántos son clickbait, en una columna."""
    positivos = sum(etiqueta for _, etiqueta in pares)
    return f"{len(pares):>6} · {_porcentaje(positivos, len(pares))}"


def entrenar(pares: list[tuple[str, int]], quitar: frozenset[str] = frozenset()):
    """La receta de producción (F3), sin los rasgos de `quitar`."""

    def analizador(titular: str) -> list[str]:
        return [rasgo for rasgo in linear.rasgos(titular) if rasgo not in quitar]

    titulares, etiquetas = titulares_y_etiquetas(pares)
    vectorizador = TfidfVectorizer(analyzer=analizador, min_df=2)
    matriz = vectorizador.fit_transform(titulares)
    return vectorizador, LogisticRegression(max_iter=1000).fit(matriz, etiquetas)


def votos(vectorizador, modelo, pares: list[tuple[str, int]]) -> list[int]:
    titulares, _ = titulares_y_etiquetas(pares)
    probabilidades = modelo.predict_proba(vectorizador.transform(titulares))[:, 1]
    return [int(probabilidad >= UMBRAL) for probabilidad in probabilidades]


def pesos_de_los_patrones(vectorizador, modelo) -> dict[str, float | None]:
    pesos = dict(
        zip(vectorizador.get_feature_names_out(), modelo.coef_[0], strict=True)
    )
    return {patron: pesos.get(patron) for patron in PATRONES}


def recuento(datos: dict) -> None:
    print("\n== 1 · Clickbait con cada patrón y sin él, en los `train`")
    print(f"  {'corpus':12} {'patrón':17} {'con él: n · clickbait':>24} {'sin él: n · clickbait':>24}")
    for corpus, clave in ENTRENAMIENTOS.items():
        pares = datos[clave]
        rasgos = [set(linear.rasgos(titular)) for titular, _ in pares]
        for patron in PATRONES:
            con = [par for par, suyos in zip(pares, rasgos, strict=True) if patron in suyos]
            sin = [par for par, suyos in zip(pares, rasgos, strict=True) if patron not in suyos]
            print(f"  {corpus:12} {patron:17} {_clickbait(con):>24} {_clickbait(sin):>24}")


def hipotesis_pregunta(datos: dict) -> None:
    print("\n== 2a · La interrogación: ¿la llevan las palabras interrogativas?")
    print("  `<question>` sólo salta con `?` al final del texto, y no en otro sitio.")
    grupos = (
        "`?` al final, con palabra interrogativa",
        "`?` al final, sin ella",
        "palabra interrogativa, sin `?`",
        "`?` en otro sitio del texto",
    )
    for corpus, clave in ENTRENAMIENTOS.items():
        repartidos: dict[str, list] = {grupo: [] for grupo in grupos}
        for par in datos[clave]:
            titular = par[0]
            rasgos = set(linear.rasgos(titular))
            pregunta = "<question>" in rasgos
            interrogativa = bool(rasgos & INTERROGATIVAS)
            if pregunta and interrogativa:
                repartidos[grupos[0]].append(par)
            elif pregunta:
                repartidos[grupos[1]].append(par)
            elif interrogativa:
                repartidos[grupos[2]].append(par)
            if not pregunta and "?" in _limpio(titular):
                repartidos[grupos[3]].append(par)
        for grupo in grupos:
            print(f"  {corpus:12} {grupo:42} {_clickbait(repartidos[grupo]):>18}")

    print("\n  Los que empiezan por palabra interrogativa: cuántos acaban en `?`")
    print("  (no todos son preguntas: «How to…» o «What happened when…» no lo son)")
    for corpus, clave in ENTRENAMIENTOS.items():
        for etiqueta, clase in ((1, "clickbait"), (0, "no clickbait")):
            empiezan = [
                titular
                for titular, suya in datos[clave]
                if suya == etiqueta and _empieza_por_interrogativa(titular)
            ]
            con_cierre = [
                titular
                for titular in empiezan
                if "<question>" in linear.rasgos(titular)
            ]
            print(
                f"  {corpus:12} {clase:13} {len(empiezan):>6} empiezan así · "
                f"{_porcentaje(len(con_cierre), len(empiezan))} acaban en `?`"
            )
    ejemplos = [
        titular
        for titular, suya in datos["chak_train"]
        if suya == 1 and _empieza_por_interrogativa(titular)
    ][:4]
    print(f"  Chakraborty, clickbait, ejemplos: {ejemplos}")


def _empieza_por_interrogativa(titular: str) -> bool:
    palabras = lexical.TOKEN.findall(_limpio(titular).lower())
    return bool(palabras) and palabras[0] in INTERROGATIVAS


def hipotesis_elipsis(datos: dict) -> None:
    print("\n== 2b · La elipsis: ¿es de recorte?")
    for corpus, clave in ENTRENAMIENTOS.items():
        con = [
            par
            for par in datos[clave]
            if lexical.PATTERNS["ellipsis"].search(_limpio(par[0]))
        ]
        al_final = [par for par in con if ELIPSIS_AL_FINAL.search(_limpio(par[0]))]
        en_medio = [par for par in con if not ELIPSIS_AL_FINAL.search(_limpio(par[0]))]
        print(
            f"  {corpus:12} al final: {_clickbait(al_final):>16}"
            f"    en medio: {_clickbait(en_medio):>16}"
        )


def hipotesis_mayusculas(datos: dict) -> None:
    print("\n== 2c · Las mayúsculas: qué palabras las disparan")
    for corpus, clave in ENTRENAMIENTOS.items():
        veces: Counter[str] = Counter()
        clickbait: Counter[str] = Counter()
        for titular, etiqueta in datos[clave]:
            for palabra in set(lexical.PATTERNS["all_caps"].findall(_limpio(titular))):
                veces[palabra] += 1
                clickbait[palabra] += int(etiqueta)
        frecuentes = ", ".join(
            f"{palabra} {cuantas} ({_porcentaje(clickbait[palabra], cuantas).strip()})"
            for palabra, cuantas in veces.most_common(10)
        )
        print(f"  {corpus:12} {sum(veces.values())} apariciones: {frecuentes}")


def pesos_por_corpus(datos: dict) -> None:
    print("\n== 3 · El peso de cada patrón, según con qué se entrene")
    chakraborty, webis, ta1c = (datos[clave] for clave in ENTRENAMIENTOS.values())
    variantes = {
        "Chakraborty": (chakraborty, frozenset()),
        "Webis-17": (webis, frozenset()),
        "TA1C": (ta1c, frozenset()),
        "Chakraborty + Webis-17": (chakraborty + webis, frozenset()),
        "los tres": (chakraborty + webis + ta1c, frozenset()),
        "los tres, sin interrogativas": (chakraborty + webis + ta1c, INTERROGATIVAS),
    }
    print(f"  {'entrenado con':30}" + "".join(f"{patron:>18}" for patron in PATRONES))
    for nombre, (pares, quitar) in variantes.items():
        vectorizador, modelo = entrenar(pares, quitar)
        pesos = pesos_de_los_patrones(vectorizador, modelo)
        print(
            f"  {nombre:30}"
            + "".join(
                f"{'sin rasgo' if pesos[patron] is None else f'{pesos[patron]:+.2f}':>18}"
                for patron in PATRONES
            )
        )
        for patron, publicado in PESOS_PUBLICADOS.get(nombre, {}).items():
            if pesos[patron] is None or abs(pesos[patron] - publicado) > TOLERANCIA:
                raise SystemExit(
                    f"ABORTADO: {nombre}, {patron}: {pesos[patron]} frente a {publicado}"
                )
    print("  control: reproduce los pesos de #78, #231 y `eval_lineal_es`")


def sin_patron(datos: dict) -> None:
    print("\n== 4 · Quitar cada patrón del bilingüe, con umbral 0,35")
    pares = sum((datos[clave] for clave in ENTRENAMIENTOS.values()), [])
    vectorizador, modelo = entrenar(pares)
    base = {}
    print("  el bilingüe entero: ", end="")
    for nombre, clave in DEVS.items():
        predichas = votos(vectorizador, modelo, datos[clave])
        _, etiquetas = titulares_y_etiquetas(datos[clave])
        base[nombre] = predichas
        f1 = f1_score(etiquetas, predichas)
        print(f"{nombre} {f1:.3f}   ", end="")
        if abs(f1 - F1_PUBLICADO[nombre]) > TOLERANCIA:
            raise SystemExit(f"ABORTADO: {nombre}: {f1} frente a {F1_PUBLICADO[nombre]}")
    print("\n  control: reproduce el F1 de #231\n")

    print(f"  {'sin':17} {'dev':17} {'F1':>6} {'diferencia':>11}   intervalo del 95 %")
    for patron in PATRONES:
        vectorizador, modelo = entrenar(pares, frozenset({patron}))
        for nombre, clave in DEVS.items():
            predichas = votos(vectorizador, modelo, datos[clave])
            _, etiquetas = titulares_y_etiquetas(datos[clave])
            diferencia, bajo, alto = diferencia_con_intervalo(
                etiquetas, predichas, base[nombre]
            )
            print(
                f"  {patron:17} {nombre:17} {f1_score(etiquetas, predichas):6.3f} "
                f"{diferencia:+11.4f}   [{bajo:+.4f}, {alto:+.4f}]",
                flush=True,
            )


def main() -> None:
    datos = cargar()
    recuento(datos)
    hipotesis_pregunta(datos)
    hipotesis_elipsis(datos)
    hipotesis_mayusculas(datos)
    pesos_por_corpus(datos)
    sin_patron(datos)


if __name__ == "__main__":
    main()
