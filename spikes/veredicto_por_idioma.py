"""#230 (2026-10-08) - ¿Cambia algo del inglés al enrutar cada señal por idioma?

El criterio de #230 es que en inglés todo quede igual. `eval_veredicto` pasa los
19.484 pares titular–cuerpo de Webis-17 por `analyze()` y guarda el resultado de
cada uno en `var/`. Su caché del 6 oct es de #78, ANTERIOR a #229, y se copió a
`veredicto_validation170630.antes-229.json` antes de rehacerla con el código de
#230. Este guion compara las dos par a par.

Un par puede cambiar por dos motivos, y los dos son de #229, no de #230:

- su titular no se detecta en inglés: ninguna señal lo analiza (en #230 ninguna
  tiene todavía modelo en español), y el veredicto pasa a `no_data`;
- su titular sí, pero su cuerpo no: la incoherencia no lo compara, y las demás
  señales quedan igual.

Cualquier otro cambio sería del enrutado de #230, y se cuenta aparte, «sin
explicar». Además, el F1 del veredicto «es clickbait» antes y ahora, en todos
los pares y en los unánimes, para leer el efecto de las dos puertas juntas.

Ejecutar desde la raíz, después de `eval_veredicto`:

    .venv/bin/python spikes/veredicto_por_idioma.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sklearn.metrics import precision_recall_fscore_support  # noqa: E402

from backend.core.idioma import INGLES, detectar  # noqa: E402
from backend.evaluation.eval_incoherencia import cargar_pares  # noqa: E402
from backend.evaluation.eval_veredicto import CACHE, POSITIVOS  # noqa: E402

ANTES = CACHE.with_name(f"{CACHE.stem}.antes-229.json")
INCOHERENCIA = "detect_clickbait_incoherence"
VEREDICTOS_POSITIVOS = {veredicto.value for veredicto in POSITIVOS}


def leer(ruta: Path) -> tuple[str, dict[str, dict]]:
    """La huella de una caché y sus filas, por id del par."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return datos["huella"], {fila["id"]: fila for fila in datos["filas"]}


def senales_que_cambian(antes: dict, ahora: dict) -> set[str]:
    """Las señales cuyo estado o voto no es el mismo."""
    return {
        nombre
        for nombre, senal in antes["senales"].items()
        if senal != ahora["senales"].get(nombre)
    }


def prf(filas: list[dict]) -> str:
    """El veredicto «es clickbait» frente a la etiqueta de Webis-17."""
    etiquetas = [fila["label"] for fila in filas]
    predichas = [int(fila["veredicto"] in VEREDICTOS_POSITIVOS) for fila in filas]
    precision, recall, f1, _ = precision_recall_fscore_support(
        etiquetas, predichas, average="binary", zero_division=0
    )
    return f"P {precision:.3f} · R {recall:.3f} · F1 {f1:.3f}  (n={len(filas)})"


def main() -> None:
    huella_antes, antes = leer(ANTES)
    huella_ahora, ahora = leer(CACHE)
    pares = {par["id"]: par for par in cargar_pares()}
    print(f"antes: {ANTES.name} · huella {huella_antes} · {len(antes)} pares")
    print(f"ahora: {CACHE.name} · huella {huella_ahora} · {len(ahora)} pares")
    if set(antes) != set(ahora):
        raise SystemExit("las dos cachés no tienen los mismos pares")

    causas: Counter[str] = Counter()
    idiomas_del_titular: Counter[str] = Counter()
    idiomas_del_cuerpo: Counter[str] = Counter()
    sin_explicar = []
    mayor_diferencia = 0.0
    comparables = []
    for identificador, fila_antes in antes.items():
        fila_ahora = ahora[identificador]
        if fila_antes.get("rechazado") or fila_ahora.get("rechazado"):
            causas["titular en blanco (la API lo rechaza)"] += 1
            continue
        comparables.append(identificador)
        par = pares[identificador]
        titular = detectar(par["headline"])
        cuerpo = detectar(par["content"])
        idiomas_del_titular[titular] += 1
        if titular == INGLES:
            idiomas_del_cuerpo[cuerpo] += 1

        if fila_antes["similitud"] is not None and fila_ahora["similitud"] is not None:
            mayor_diferencia = max(
                mayor_diferencia, abs(fila_antes["similitud"] - fila_ahora["similitud"])
            )

        cambian = senales_que_cambian(fila_antes, fila_ahora)
        if not cambian and fila_antes["veredicto"] == fila_ahora["veredicto"]:
            causas["igual"] += 1
        elif titular != INGLES:
            causas[f"cambia: titular en «{titular}» (#229)"] += 1
        elif cuerpo != INGLES and cambian == {INCOHERENCIA}:
            causas[f"cambia: cuerpo en «{cuerpo}», sólo la incoherencia (#229)"] += 1
        else:
            causas["cambia: SIN EXPLICAR"] += 1
            sin_explicar.append(
                (
                    identificador,
                    sorted(cambian),
                    fila_antes["veredicto"],
                    fila_ahora["veredicto"],
                )
            )

    print("\n== idioma detectado")
    print(f"  del titular: {dict(idiomas_del_titular.most_common())}")
    print(
        f"  del cuerpo, con el titular en inglés: {dict(idiomas_del_cuerpo.most_common())}"
    )

    print("\n== cada par, antes y ahora")
    for causa, cuantos in causas.most_common():
        print(f"  {causa}: {cuantos}")
    print(
        f"  la mayor diferencia de similitud, donde se calculó las dos veces: {mayor_diferencia:.2e}"
    )
    for identificador, cambian, veredicto_antes, veredicto_ahora in sin_explicar[:10]:
        print(
            f"    {identificador}: {cambian} · {veredicto_antes} -> {veredicto_ahora}"
        )

    print("\n== el veredicto «es clickbait» frente a la etiqueta")
    for nombre, filas in [("antes", antes), ("ahora", ahora)]:
        todas = [filas[identificador] for identificador in comparables]
        unanimes = [fila for fila in todas if fila["unanime"]]
        print(f"  {nombre}: todos {prf(todas)} · unánimes {prf(unanimes)}")


if __name__ == "__main__":
    main()
