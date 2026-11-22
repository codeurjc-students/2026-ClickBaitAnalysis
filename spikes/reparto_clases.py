"""#256 (2026-10-22) - Cuántos titulares y cuánto clickbait hay en cada parte.

La pauta de la cotutora para 5.1 pide tablas que muestren «numéricamente la
distribución de clases y el tamaño de cada partición». El README da el tamaño
de todas, pero el reparto de clases sólo el de TA1C, en porcentaje, y el de
`webis_test`. Este guion lo cuenta en todas.

Lee sólo lo versionado en `data/`, con las funciones del propio proyecto, para
que lo contado sea lo que se usó. `train170331` sale de `cargar_datos()`, de
`eval_reentreno.py`, que le quita el tuit que comparte con `validation170630`,
igual que al entrenar el lineal. Comprueba además que las partes sumen el
corpus entero y que los tamaños sean los que cita el README.

No mide ningún modelo: sólo cuenta etiquetas. Contar el clickbait de un `test`
no es abrirlo, porque no se decide nada con ello.

Ejecutar desde la raíz: .venv/bin/python spikes/reparto_clases.py

Resultados (2026-10-22, con los datos de `df07f15`):

| Corpus | Parte | Titulares | Clickbait | No clickbait | Clickbait (%) |
|---|---|---|---|---|---|
| Chakraborty | train | 19.200 | 9.599 | 9.601 | 50,0 % |
| Chakraborty | dev | 6.400 | 3.200 | 3.200 | 50,0 % |
| Chakraborty | test | 6.400 | 3.200 | 3.200 | 50,0 % |
| Webis-17 | train170331, sin el tuit repetido | 2.458 | 762 | 1.696 | 31,0 % |
| Webis-17 | webis_dev | 3.896 | 943 | 2.953 | 24,2 % |
| Webis-17 | webis_test | 15.588 | 3.773 | 11.815 | 24,2 % |
| TA1C | train | 2.100 | 591 | 1.509 | 28,1 % |
| TA1C | validation | 700 | 206 | 494 | 29,4 % |
| TA1C | test | 700 | 204 | 496 | 29,1 % |

Los corpus enteros: Chakraborty, 32.000 (15.999 clickbait, 50,0 %);
`validation170630`, 19.484 (4.716, 24,2 %); y TA1C, 3.500 (1.001, 28,6 %).
Las partes los suman, y todos los tamaños son los que cita el README.
"""

import gzip
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.evaluation.eval_external import load_records  # noqa: E402
from backend.evaluation.eval_lexical import load_dataset  # noqa: E402
from backend.evaluation.eval_reentreno import cargar_datos  # noqa: E402
from backend.evaluation.splits import load_split  # noqa: E402
from backend.evaluation.ta1c_extract import DESTINO_TEASERS  # noqa: E402

WEBIS_TRAIN = "train170331, sin el tuit repetido"

# Lo que cita el README, para comprobar que se cuenta lo mismo que se usó.
TAMANOS_DEL_README = {
    ("Chakraborty", "train"): 19_200,
    ("Chakraborty", "dev"): 6_400,
    ("Chakraborty", "test"): 6_400,
    ("Webis-17", WEBIS_TRAIN): 2_458,
    ("Webis-17", "webis_dev"): 3_896,
    ("Webis-17", "webis_test"): 15_588,
    ("TA1C", "train"): 2_100,
    ("TA1C", "validation"): 700,
    ("TA1C", "test"): 700,
}
CLICKBAIT_DEL_README = {("Webis-17", "webis_test"): 3_773}


def contar(etiquetas: list[int]) -> tuple[int, int]:
    """Cuántos hay y cuántos son clickbait (la etiqueta 1)."""
    desconocidas = set(etiquetas) - {0, 1}
    if desconocidas:
        raise SystemExit(f"Hay etiquetas que no son 0 ni 1: {sorted(desconocidas)}")
    return len(etiquetas), sum(etiquetas)


def etiquetas_de(pares: list[tuple[str, int]]) -> list[int]:
    return [int(etiqueta) for _, etiqueta in pares]


def etiquetas_de_registros(registros: list[dict]) -> list[int]:
    return [int(registro["label"]) for registro in registros]


def leer_ta1c() -> list[dict]:
    with gzip.open(DESTINO_TEASERS, "rt", encoding="utf-8") as fichero:
        return [json.loads(linea) for linea in fichero]


def miles(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def porcentaje(parte: int, total: int) -> str:
    return f"{100 * parte / total:.1f}".replace(".", ",") + " %"


def comprobar(descripcion: str, contado: int, esperado: int) -> bool:
    cuadra = contado == esperado
    veredicto = "cuadra" if cuadra else "NO CUADRA"
    print(f"- {descripcion}: {miles(contado)} (esperado {miles(esperado)}), {veredicto}")
    return cuadra


def main() -> None:
    datos_del_lineal = cargar_datos()
    partes = {
        ("Chakraborty", "train"): etiquetas_de(load_split("train")),
        ("Chakraborty", "dev"): etiquetas_de(load_split("dev")),
        ("Chakraborty", "test"): etiquetas_de(load_split("test")),
        ("Webis-17", WEBIS_TRAIN): etiquetas_de(datos_del_lineal["webis_train"]),
        ("Webis-17", "webis_dev"): etiquetas_de(load_split("webis_dev")),
        ("Webis-17", "webis_test"): etiquetas_de(load_split("webis_test")),
        ("TA1C", "train"): etiquetas_de(load_split("ta1c_train")),
        ("TA1C", "validation"): etiquetas_de(load_split("ta1c_validation")),
        ("TA1C", "test"): etiquetas_de(load_split("ta1c_test")),
    }
    recuentos = {clave: contar(etiquetas) for clave, etiquetas in partes.items()}

    print("| Corpus | Parte | Titulares | Clickbait | No clickbait | Clickbait (%) |")
    print("|---|---|---|---|---|---|")
    for (corpus, parte), (total, clickbait) in recuentos.items():
        print(
            f"| {corpus} | {parte} | {miles(total)} | {miles(clickbait)} "
            f"| {miles(total - clickbait)} | {porcentaje(clickbait, total)} |"
        )

    print()
    print("Comprobaciones:")
    todo_cuadra = True
    for (corpus, parte), esperado in TAMANOS_DEL_README.items():
        contado = recuentos[(corpus, parte)][0]
        todo_cuadra &= comprobar(f"{corpus} {parte}, tamaño del README", contado, esperado)
    for (corpus, parte), esperado in CLICKBAIT_DEL_README.items():
        contado = recuentos[(corpus, parte)][1]
        todo_cuadra &= comprobar(f"{corpus} {parte}, clickbait del README", contado, esperado)
    todo_cuadra &= comprobar("tuits quitados de train170331", datos_del_lineal["quitados"], 1)

    corpus_enteros = [
        ("Chakraborty", "el corpus entero", etiquetas_de(load_dataset()), ("train", "dev", "test")),
        (
            "Webis-17",
            "validation170630",
            etiquetas_de_registros(load_records("validation170630")),
            ("webis_dev", "webis_test"),
        ),
        ("TA1C", "el extracto entero", etiquetas_de_registros(leer_ta1c()), ("train", "validation", "test")),
    ]
    for corpus, nombre, etiquetas, nombres_de_partes in corpus_enteros:
        total, clickbait = contar(etiquetas)
        suma_de_titulares = sum(recuentos[(corpus, parte)][0] for parte in nombres_de_partes)
        suma_de_clickbait = sum(recuentos[(corpus, parte)][1] for parte in nombres_de_partes)
        todo_cuadra &= comprobar(f"{corpus}: las partes suman {nombre}, en titulares", suma_de_titulares, total)
        todo_cuadra &= comprobar(f"{corpus}: las partes suman {nombre}, en clickbait", suma_de_clickbait, clickbait)
        print(f"  {corpus}, {nombre}: {miles(total)} titulares, {miles(clickbait)} clickbait ({porcentaje(clickbait, total)})")

    print()
    print("Todo cuadra." if todo_cuadra else "Algo NO CUADRA: mirar arriba.")


if __name__ == "__main__":
    main()
