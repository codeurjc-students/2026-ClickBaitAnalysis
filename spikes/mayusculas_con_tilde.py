"""#231 (2026-10-08) - ¿En cuántos titulares cambia el patrón de mayúsculas?

El patrón `all_caps` del léxico era `\\b[A-Z]{4,}\\b`, y en español no veía
«ÚLTIMA» ni «ESPAÑA»: la letra con tilde corta la secuencia y no deja frontera
de palabra. Desde #231 es `\\b[A-ZÁÉÍÓÚÜÑ]{4,}\\b`. Lo usan el léxico y los
rasgos del lineal (`linear.rasgos`), así que el cambio toca también al inglés.

Este guion cuenta, parte a parte, en cuántos titulares los dos patrones dicen
cosas distintas:

- en inglés (Chakraborty y Webis-17), para saber si las cifras medidas del
  léxico y del lineal siguen valiendo;
- en TA1C, para saber cuánto aporta el cambio a los tuits en español.

El patrón de antes va escrito aquí, como la regla de antes de #124 en
`eval_veredicto`: importar el de `lexical` ya no lo reproduciría.

    .venv/bin/python -m spikes.mayusculas_con_tilde
"""

import re

from backend.evaluation.eval_external import load_external
from backend.evaluation.splits import load_split
from backend.integrations.nlp import lexical

ANTES = re.compile(r"\b[A-Z]{4,}\b")
AHORA = lexical.PATTERNS["all_caps"]
EJEMPLOS = 3

PARTES = {
    "Chakraborty": ("train", "dev", "test"),
    "Webis-17": ("train170331", "webis_dev", "webis_test"),
    "TA1C": ("ta1c_train", "ta1c_validation", "ta1c_test"),
}


def titulares(parte: str) -> list[str]:
    if parte == "train170331":
        return [titular for titular, _, _ in load_external(parte)]
    return [titular for titular, _ in load_split(parte)]


def main() -> None:
    print(f"antes: {ANTES.pattern}   ahora: {AHORA.pattern}\n")
    for corpus, partes in PARTES.items():
        for parte in partes:
            lista = titulares(parte)
            ganan = [
                titular
                for titular in lista
                if AHORA.search(titular) and not ANTES.search(titular)
            ]
            pierden = [
                titular
                for titular in lista
                if ANTES.search(titular) and not AHORA.search(titular)
            ]
            con_mayusculas = sum(1 for titular in lista if AHORA.search(titular))
            print(
                f"{corpus:12} {parte:16} {len(lista):6} titulares · "
                f"con mayúsculas ahora {con_mayusculas:5} ({con_mayusculas / len(lista):5.1%}) · "
                f"las ganan {len(ganan):4} ({len(ganan) / len(lista):5.2%}) · "
                f"las pierden {len(pierden)}"
            )
            for titular in ganan[:EJEMPLOS]:
                print(f"      + {titular[:110]}")


if __name__ == "__main__":
    main()
