"""Las cifras del veredicto inglés que cita la memoria, de la caché de `eval_veredicto`.

16 nov 2026, PR #298. Al repasar la memoria salieron cifras del veredicto inglés
que ninguna sección del README publicaba: el F1 del lineal y el de la
incoherencia sobre los 19.484 tuits, la precisión y el recall del veredicto, y el
reparto de sus etiquetas con el clickbait que hay dentro de cada una. Salían de
`eval_veredicto` (#124), que guarda el voto de cada señal por tuit en una caché,
pero su salida no se guardó. Este guion las cuenta otra vez desde esa caché, sin
cargar ningún modelo, y su salida queda en `spikes/cifras_veredicto/`.

La caché vive en `var/`, sin versionar, y es la del 8 oct, anterior a BETO
(#242): en ella la dedicada no vota los 26 tuits que el detector de idioma no
toma por ingleses, y hoy votaría los que toma por españoles. Con el sistema de
hoy podrían cambiar, como mucho, esos 26 de 19.484. Dos cifras ya publicadas la
atan a lo que se midió: la dedicada tiene que dar 0,758 (#124) y el veredicto,
0,660 (#231). Si no, la caché es de otro sistema y el guion se para.

Desde #215 (21 nov 2026) la caché se regeneró sobre la versión congelada
(`79f029e`), y la del 8 oct quedó en
`var/veredicto_validation170630.antes-215.json`. El control va por la huella
de cada caché (`CONTROLES`): cada una, con lo que se publicó de ella. Una
caché de huella desconocida no se para, pero lo dice: nada publicado la ata.

Las señales se miden sobre los tuits en que votaron, como en
`eval_veredicto.comprobar`; el veredicto, sobre todos, con `deceptive` y
`stylistic_clickbait` como «es clickbait» y lo demás como «no». Los 19.484 son
el trozo grande de Webis-Clickbait-17, que desde la partición de #78 incluye
`webis_test`: no son cifras de un test reservado.

Ejecutar desde la raíz:

    .venv/bin/python spikes/cifras_veredicto.py [caché] | tee spikes/cifras_veredicto/<fecha>.txt

Sin argumento lee la de `var/`; la del 8 oct, con su ruta.

Resultados (2026-11-16, con la caché del 8 oct, huella 3db32ea91cb2):

| Señal | Votan | P | R | F1 |
|---|---|---|---|---|
| Dedicada (control) | 19.458 | 0,709 | 0,814 | 0,758 |
| Léxico | 19.458 | 0,341 | 0,656 | 0,448 |
| Lineal bilingüe | 19.475 | 0,404 | 0,751 | 0,526 |
| Incoherencia | 19.439 | 0,666 | 0,205 | 0,314 |

El veredicto (control): P 0,690, R 0,633 y F1 0,660 en los 19.484; 0,811 en
los 6.808 unánimes.

| Etiqueta | Tuits | Del total | Clickbait dentro |
|---|---|---|---|
| factual | 6.952 | 35,7 % | 4,4 % |
| ambiguous | 8.194 | 42,1 % | 17,4 % |
| stylistic_clickbait | 2.990 | 15,3 % | 68,0 % |
| deceptive | 1.339 | 6,9 % | 71,2 % |
| no_data | 9 | 0,0 % | 66,7 % |

Resultados (2026-11-21, #215, con la caché regenerada sobre `79f029e`, huella
c5755af33a53; la salida, en `spikes/cifras_veredicto/2026-11-21.txt`): la
dedicada vota 19.475 tuits, 17 más, los que el detector toma por españoles
(los vota BETO; quedan 9 de idioma indeterminado), y sigue en F1 0,758. El
léxico, el lineal, la incoherencia y el veredicto en los 19.484 no cambian. En
los unánimes, el veredicto pasa de 0,811 a 0,812, y en el reparto cambian dos
filas: `ambiguous`, 8.199 (42,1 %, 17,3 % de clickbait), y
`stylistic_clickbait`, 2.985 (15,3 %, 68,1 %).
"""

import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sklearn.metrics import precision_recall_fscore_support

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "var" / "veredicto_validation170630.json"

TUITS = 19_484
# Lo ya publicado de cada caché, por su huella: la ata a lo que se midió.
CONTROLES = {
    # La del 8 oct: la dedicada, de #124, y el veredicto, de #231.
    "3db32ea91cb2": {"dedicada": 0.758, "veredicto": 0.660},
    # La de la versión congelada, `79f029e` (#215).
    "c5755af33a53": {"dedicada": 0.758, "veredicto": 0.660},
}

SENALES = {
    "Dedicada (control)": "detect_clickbait",
    "Léxico": "detect_clickbait_lexical",
    "Lineal bilingüe": "detect_clickbait_linear",
    "Incoherencia": "detect_clickbait_incoherence",
}
POSITIVOS = {"deceptive", "stylistic_clickbait"}
ETIQUETAS = ("factual", "ambiguous", "stylistic_clickbait", "deceptive", "no_data")


def _coma(valor: float) -> str:
    return f"{valor:.3f}".replace(".", ",")


def _porcentaje(parte: int, total: int) -> str:
    return f"{100 * parte / total:.1f}".replace(".", ",") + " %" if total else "-"


def _miles(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def _git(*argumentos: str) -> str:
    salida = subprocess.run(
        ["git", *argumentos], cwd=RAIZ, capture_output=True, text=True, check=False
    )
    return salida.stdout.strip()


def _commit() -> str:
    """El commit de la copia, y si este guion aún no está en él."""
    sin_commitear = _git("status", "--porcelain", "--", str(Path(__file__).resolve()))
    return _git("rev-parse", "--short", "HEAD") + (
        ", con este guion sin commitear" if sin_commitear else ""
    )


def cargar(ruta: Path) -> tuple[dict, bytes]:
    """La caché entera y sus bytes, comprobada contra los 19.484 tuits."""
    contenido = ruta.read_bytes()
    cache = json.loads(contenido)
    if len(cache["ids"]) != TUITS or len(cache["filas"]) != TUITS:
        raise SystemExit(f"la caché no tiene los {TUITS} tuits del trozo grande")
    if any(fila.get("rechazado") for fila in cache["filas"]):
        raise SystemExit("la caché tiene tuits rechazados: la cuenta no sería ésta")
    return cache, contenido


def medir(etiquetas: list[int], predichas: list[int]) -> tuple[float, float, float]:
    """Precisión, recall y F1 de la clase clickbait."""
    precision, recall, f1, _ = precision_recall_fscore_support(
        etiquetas, predichas, average="binary", zero_division=0
    )
    return precision, recall, f1


def medir_senal(filas: list[dict], senal: str) -> dict:
    """Una señal, sobre los tuits en que votó, con el recuento de sus estados."""
    votaron = [fila for fila in filas if fila["senales"][senal]["voto"] is not None]
    precision, recall, f1 = medir(
        [fila["label"] for fila in votaron],
        [int(fila["senales"][senal]["voto"]) for fila in votaron],
    )
    return {
        "votan": len(votaron),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "estados": dict(Counter(fila["senales"][senal]["estado"] for fila in filas)),
    }


def medir_veredicto(filas: list[dict]) -> dict[str, tuple[int, float, float, float]]:
    """El veredicto como «es clickbait» o no, en todos los tuits y en los unánimes."""
    grupos = {
        "todos": filas,
        "unánimes": [fila for fila in filas if fila["unanime"]],
    }
    return {
        nombre: (
            len(grupo),
            *medir(
                [fila["label"] for fila in grupo],
                [int(fila["veredicto"] in POSITIVOS) for fila in grupo],
            ),
        )
        for nombre, grupo in grupos.items()
    }


def reparto(filas: list[dict]) -> list[tuple[str, int, int]]:
    """Cuántos tuits caen en cada etiqueta, y cuántos de ellos son clickbait."""
    etiquetados = Counter(fila["veredicto"] for fila in filas)
    clickbait = Counter(fila["veredicto"] for fila in filas if fila["label"] == 1)
    desconocidas = set(etiquetados) - set(ETIQUETAS)
    if desconocidas:
        raise SystemExit(f"etiquetas que el guion no conoce: {sorted(desconocidas)}")
    return [
        (etiqueta, etiquetados[etiqueta], clickbait[etiqueta]) for etiqueta in ETIQUETAS
    ]


def main() -> None:
    ruta = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else CACHE
    cache, contenido = cargar(ruta)
    filas = cache["filas"]
    modificada = datetime.fromtimestamp(ruta.stat().st_mtime, tz=UTC)

    senales = {nombre: medir_senal(filas, senal) for nombre, senal in SENALES.items()}
    veredicto = medir_veredicto(filas)
    dedicada = senales["Dedicada (control)"]["f1"]
    _, _, _, f1_veredicto = veredicto["todos"]
    control = CONTROLES.get(cache["huella"])
    if control is not None:
        if round(dedicada, 3) != control["dedicada"]:
            raise SystemExit(
                f"control: la dedicada da {dedicada:.4f}, y no {control['dedicada']}"
            )
        if round(f1_veredicto, 3) != control["veredicto"]:
            raise SystemExit(
                f"control: el veredicto da {f1_veredicto:.4f}, "
                f"y no {control['veredicto']}"
            )

    print("== condiciones")
    print(f"  fecha: {datetime.now(UTC).isoformat(timespec='seconds')}")
    print(f"  commit: {_commit()}")
    print(f"  caché: {ruta.relative_to(RAIZ)}, {_miles(len(contenido))} bytes")
    print(f"  sha256: {hashlib.sha256(contenido).hexdigest()}")
    print(f"  modificada: {modificada.isoformat(timespec='seconds')}")
    print(f"  huella del sistema que la generó: {cache['huella']}")
    if control is None:
        print("  control: ninguno; ninguna cifra publicada ata esta caché")
    else:
        print(f"  control: {control}, cumplido")
    print(f"  tuits: {_miles(len(filas))}")

    print("\n== las señales, sobre los tuits en que votaron")
    print("| Señal | Votan | P | R | F1 | Estados |")
    print("|---|---|---|---|---|---|")
    for nombre, medida in senales.items():
        print(
            f"| {nombre} | {_miles(medida['votan'])} | {_coma(medida['precision'])} | "
            f"{_coma(medida['recall'])} | {_coma(medida['f1'])} | {medida['estados']} |"
        )

    print("\n== el veredicto, con deceptive y stylistic_clickbait como «es clickbait»")
    print("| Tuits | Cuántos | P | R | F1 |")
    print("|---|---|---|---|---|")
    for nombre, (cuantos, precision, recall, f1) in veredicto.items():
        print(
            f"| {nombre} | {_miles(cuantos)} | {_coma(precision)} | "
            f"{_coma(recall)} | {_coma(f1)} |"
        )

    print("\n== el reparto de las etiquetas, y el clickbait dentro de cada una")
    print("| Etiqueta | Tuits | Del total | Clickbait dentro |")
    print("|---|---|---|---|")
    for etiqueta, cuantos, clickbait in reparto(filas):
        print(
            f"| {etiqueta} | {_miles(cuantos)} | {_porcentaje(cuantos, len(filas))} | "
            f"{_porcentaje(clickbait, cuantos)} |"
        )


if __name__ == "__main__":
    main()
