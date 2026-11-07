"""#256 (2026-11-07) - ¿Cuánto cuesta cada señal, en la CPU de producción?

La discusión de la memoria (5.4) tiene que poner al lado lo que acierta cada
enfoque y lo que cuesta. Hasta aquí sólo se conocía el análisis entero, 0,11 s
en caliente (#156: con tres modelos, antes del español, sin guion y sin decir
en qué máquina), y BETO suelto, 0,076 s por titular (#242, en el PC). Este
guion mide cada señal por separado.

QUÉ SE MIDE, Y POR QUÉ ASÍ

- **Cada fila, en su proceso.** Importar torch y la primera inferencia son
  costes globales (#125): en un mismo proceso se los llevaría la primera señal.
  `importar_s` es importar el orquestador, y `librerias_s`, lo que esa señal
  necesita además (torch y compañía). Las dos señales sin modelo no pagan esto
  por sí mismas, y por eso se separa.
- **Por el camino de producción**: `_Signal.run`, lo que llama `_run_signals`, y
  no el modelo suelto (#188). El análisis entero, por `analyze()`, después de
  `precalentar()`. Las señales de texto pasan por `asyncio.to_thread`, como en
  una petición.
- **El protocolo de #232 y #242**: 3 titulares de calentamiento y 100 medidos,
  de uno en uno, con la mediana y el p95 calculados igual.
- **`primera_llamada_s`** es la carga del modelo y su primera inferencia, sin
  separar, en una señal. En el análisis entero, `precalentar()`, que carga los
  modelos de los dos idiomas.
- **La memoria**, de `/proc/self/status`, separando la propia (`RssAnon`) de la
  respaldada por ficheros (`RssFile`): la segunda se puede compartir entre
  procesos, y `docker stats` no la cuenta (#164).

Los titulares son los 100 primeros de TA1C `validation`, los mismos que midieron
#232 y #242, y los 100 primeros de `webis_dev` con su cuerpo, que necesita la
incoherencia. No llevan etiqueta: aquí no se acierta nada, y ningún `test` se
toca. La muestra no se versiona, porque los cuerpos de Webis-17 no lo están
(#121).

Se niega a medir si ve una GPU: producción va en CPU, y en WSL `transformers`
usaría la GTX sin que nadie se lo pida (#159). Y una señal que falle aborta la
fila: mediría el camino del error.

PARTES

    python spikes/coste_senales.py muestra <fichero.json>
    python spikes/coste_senales.py filas
    python spikes/coste_senales.py medir <fila> <fichero.json>
    python spikes/coste_senales.py resumen <fichero.jsonl> [...]

`medir` escribe una línea que empieza por `COSTE `, porque por la misma salida
van los registros de `structlog`. Lo lanza `spikes/coste_senales.sh`, una fila
por contenedor, y sin él, en el PC:

    CUDA_VISIBLE_DEVICES= .venv/bin/python spikes/coste_senales.py medir dedicada-es /tmp/muestra.json

Resultados (2026-11-07, en la máquina 1, imagen `23de028871d4`, de `0f0d4fb`,
tres pasadas; la mediana de cada cifra). Sale de `resumen`, con los datos de
`spikes/coste_senales/`:

| Fila | Primera llamada (s) | Por titular (ms) | p95 (ms) | Memoria (MiB) | Propia | Ficheros |
|---|---|---|---|---|---|---|
| Léxico | 0,01 | 0,15 | 0,18 | 51 | 36 | 15 |
| Lineal, inglés | 0,06 | 0,23 | 0,27 | 54 | 39 | 15 |
| Lineal, español | 0,04 | 0,19 | 0,25 | 53 | 38 | 15 |
| Dedicada, inglés | 3,42 | 35,91 | 47,69 | 849 | 365 | 484 |
| Dedicada, español | 3,30 | 42,81 | 69,56 | 844 | 349 | 496 |
| Tono, inglés | 3,37 | 34,57 | 40,43 | 828 | 344 | 484 |
| Tono, español | 3,42 | 29,15 | 43,95 | 836 | 478 | 358 |
| Incoherencia | 0,33 | 54,23 | 64,01 | 593 | 387 | 206 |
| Análisis entero, inglés | 1,48 | 124,69 | 137,66 | 2.167 | 745 | 1.422 |
| Análisis entero, español | 1,50 | 84,19 | 130,25 | 2.160 | 727 | 1.433 |

Importar el orquestador cuesta unos 0,45 s, y las librerías, 3,3 s con un modelo
de `transformers` y 6,4 s si entra `sentence_transformers`. Se apartan más de un
20 % de su mediana el léxico y los dos lineales, por menos de 0,2 ms. La primera
llamada no es un arranque en frío: antes de empezar, entre el 69 y el 100 % de
los pesos estaba en la caché de disco.

En inglés, el análisis entero es la suma de sus señales (125 ms). En español no:
faltan 12 ms, observado y sin explicar.
"""

import asyncio
import importlib
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.core.idioma import ESPANOL, INGLES  # noqa: E402

# Los mismos de #232 y #242 (`MUESTRA_TIEMPO` y `CALENTAMIENTO`).
TITULARES = 100
CALENTAMIENTO = 3

CAMPOS_DE_MEMORIA = ("VmRSS", "VmHWM", "RssAnon", "RssFile")

CON_PIPELINE = ("torch", "transformers")
CON_EMBEDDINGS = ("torch", "sentence_transformers")
TODAS = ("torch", "transformers", "sentence_transformers")


@dataclass(frozen=True)
class Fila:
    """Una fila de la tabla. Sin `senal`, es `analyze()` entero."""

    senal: str | None
    idioma: str
    librerias: tuple[str, ...]


FILAS = {
    "lexico-en": Fila("detect_clickbait_lexical", INGLES, ()),
    "lineal-en": Fila("detect_clickbait_linear", INGLES, ()),
    "lineal-es": Fila("detect_clickbait_linear", ESPANOL, ()),
    "dedicada-en": Fila("detect_clickbait", INGLES, CON_PIPELINE),
    "dedicada-es": Fila("detect_clickbait", ESPANOL, CON_PIPELINE),
    "tono-en": Fila("analyze_sentiment", INGLES, CON_PIPELINE),
    "tono-es": Fila("analyze_sentiment", ESPANOL, CON_PIPELINE),
    "incoherencia-en": Fila("detect_clickbait_incoherence", INGLES, CON_EMBEDDINGS),
    "analisis-en": Fila(None, INGLES, TODAS),
    "analisis-es": Fila(None, ESPANOL, TODAS),
}


def muestra(ruta: Path) -> None:
    """Los titulares que se miden, sin etiquetas. Se ejecuta en WSL: `evaluation/`
    y los cuerpos de Webis-17 no están en la imagen."""
    from backend.evaluation.eval_incoherencia import cargar_pares
    from backend.evaluation.splits import _path, load_split

    cuerpos = {par["id"]: par["content"] for par in cargar_pares()}
    with _path("webis_dev").open(encoding="utf-8") as fichero:
        filas = [json.loads(linea) for linea in fichero]
    en_ingles = [
        {"titular": fila["headline"], "cuerpo": cuerpos[fila["id"]]}
        for fila in filas
        if fila["id"] in cuerpos
    ][:TITULARES]
    en_espanol = [
        {"titular": titular} for titular, _ in load_split("ta1c_validation")[:TITULARES]
    ]
    if len(en_ingles) != TITULARES or len(en_espanol) != TITULARES:
        raise SystemExit(f"faltan titulares: {len(en_ingles)} y {len(en_espanol)}")
    ruta.write_text(
        json.dumps({INGLES: en_ingles, ESPANOL: en_espanol}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"{TITULARES} en cada idioma: {ruta}")


def _memoria() -> dict[str, int]:
    """La del proceso en este momento, en MiB."""
    medida = {}
    for linea in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        campo, _, valor = linea.partition(":")
        if campo in CAMPOS_DE_MEMORIA:
            medida[campo] = round(int(valor.split()[0]) / 1024)
    return medida


def _procesador() -> str:
    with open("/proc/cpuinfo", encoding="utf-8") as fichero:
        return next(
            linea.split(":", 1)[1].strip()
            for linea in fichero
            if linea.startswith("model name")
        )


def _version(paquete: str) -> str:
    return getattr(sys.modules.get(paquete), "__version__", "no cargado")


def _llamada(fila: Fila, orquestador):
    """Lo que se cronometra: una petición de esta fila, por el camino de
    producción. Aborta si falla, para no medir el camino del error."""
    from backend.analysis.domain import AnalyzeRequest, SignalStatus

    if fila.senal is None:

        async def analizar(entrada: dict) -> None:
            respuesta = await orquestador.analyze(
                AnalyzeRequest(
                    headline=entrada["titular"], content=entrada.get("cuerpo")
                )
            )
            fallidas = [
                senal.name
                for senal in respuesta.signals
                if senal.status == SignalStatus.ERROR
            ]
            if fallidas:
                raise SystemExit(f"han fallado {fallidas}: {entrada['titular']}")

        return analizar

    especificacion = next(
        spec for spec in orquestador._SIGNALS if spec.name == fila.senal
    )

    async def ejecutar(entrada: dict) -> None:
        resultado = await especificacion.run(
            entrada["titular"], entrada.get("cuerpo"), fila.idioma
        )
        if not resultado.success:
            raise SystemExit(f"{fila.senal}: {resultado.error}")

    return ejecutar


async def medir(nombre: str, ruta_muestra: Path) -> None:
    fila = FILAS[nombre]
    entradas = json.loads(ruta_muestra.read_text(encoding="utf-8"))[fila.idioma]
    carga_del_sistema = os.getloadavg()[0]

    inicio = time.perf_counter()
    from backend.analysis import orchestrator as orquestador

    importar_s = time.perf_counter() - inicio

    inicio = time.perf_counter()
    for libreria in fila.librerias:
        importlib.import_module(libreria)
    librerias_s = time.perf_counter() - inicio

    hilos = None
    if fila.librerias:
        import torch

        if torch.cuda.is_available():
            raise SystemExit(
                "La GPU está a la vista: lánzalo con CUDA_VISIBLE_DEVICES=, como producción."
            )
        hilos = torch.get_num_threads()

    memoria_al_empezar = _memoria()
    llamar = _llamada(fila, orquestador)

    inicio = time.perf_counter()
    precalentado = None
    if fila.senal is None:
        precalentado = await orquestador.precalentar()
        if min(precalentado.values()) < 0:
            raise SystemExit(f"el precalentado ha fallado: {precalentado}")
    else:
        await llamar(entradas[0])
    primera_llamada_s = time.perf_counter() - inicio

    for entrada in entradas[:CALENTAMIENTO]:
        await llamar(entrada)

    segundos = []
    for entrada in entradas:
        inicio = time.perf_counter()
        await llamar(entrada)
        segundos.append(time.perf_counter() - inicio)
    segundos.sort()

    ficha = None
    if fila.senal is not None:
        from backend.integrations.nlp.model_cards import ficha_declarada

        ficha = ficha_declarada(fila.senal, fila.idioma)

    medida = {
        "fila": nombre,
        "senal": fila.senal,
        "idioma": fila.idioma,
        "modelo": ficha["model_id"] if ficha else None,
        "revision": ficha["revision"] if ficha else None,
        "titulares": len(segundos),
        "importar_s": round(importar_s, 3),
        "librerias_s": round(librerias_s, 3),
        "primera_llamada_s": round(primera_llamada_s, 3),
        "precalentado_s": precalentado,
        "mediana_s": statistics.median(segundos),
        "p95_s": segundos[int(0.95 * len(segundos)) - 1],
        "maximo_s": segundos[-1],
        "memoria_al_empezar_mib": memoria_al_empezar,
        "memoria_al_terminar_mib": _memoria(),
        "condiciones": {
            "procesador": _procesador(),
            "nucleos": os.cpu_count(),
            "hilos_de_torch": hilos,
            "carga_del_sistema": carga_del_sistema,
            "python": platform.python_version(),
            "torch": _version("torch"),
            "transformers": _version("transformers"),
            "sentence_transformers": _version("sentence_transformers"),
        },
    }
    print("COSTE " + json.dumps(medida, ensure_ascii=False), flush=True)


def _milisegundos(segundos: float) -> str:
    return f"{segundos * 1000:.2f}".replace(".", ",")


def _segundos(segundos: float) -> str:
    return f"{segundos:.2f}".replace(".", ",")


def _columna(pasadas: list[dict], leer) -> str:
    return " · ".join(leer(pasada) for pasada in pasadas)


def _mediana(pasadas: list[dict], leer) -> float:
    return statistics.median(leer(pasada) for pasada in pasadas)


def _se_aparta(pasadas: list[dict]) -> float:
    """Lo que más se aleja una pasada de la mediana, en tanto por ciento."""
    centro = _mediana(pasadas, lambda medida: medida["mediana_s"])
    return 100 * max(abs(medida["mediana_s"] - centro) / centro for medida in pasadas)


def _tabla_de_medianas(medidas: dict[str, list[dict]]) -> None:
    """La que se cita: la mediana de las pasadas, como dice el protocolo
    publicado en #256, y qué filas se apartan más de un 20 %."""
    print(
        "| Fila | Librerías (s) | Primera llamada (s) | Mediana (ms) | p95 (ms) "
        "| Memoria (MiB) | Propia (MiB) | Ficheros (MiB) | Se aparta |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for nombre in FILAS:
        pasadas = medidas.get(nombre, [])
        if not pasadas:
            continue
        print(
            f"| {nombre} "
            f"| {_segundos(_mediana(pasadas, lambda medida: medida['librerias_s']))} "
            f"| {_segundos(_mediana(pasadas, lambda medida: medida['primera_llamada_s']))} "
            f"| {_milisegundos(_mediana(pasadas, lambda medida: medida['mediana_s']))} "
            f"| {_milisegundos(_mediana(pasadas, lambda medida: medida['p95_s']))} "
            f"| {_mediana(pasadas, lambda medida: medida['memoria_al_terminar_mib']['VmRSS']):.0f} "
            f"| {_mediana(pasadas, lambda medida: medida['memoria_al_terminar_mib']['RssAnon']):.0f} "
            f"| {_mediana(pasadas, lambda medida: medida['memoria_al_terminar_mib']['RssFile']):.0f} "
            f"| {_se_aparta(pasadas):.0f} % |"
        )


def resumen(rutas: list[Path]) -> None:
    """Las dos tablas, sin ejecutar nada. La primera, con las pasadas de cada
    cifra separadas por « · », para que se vea cuánto se mueven; la segunda, con
    su mediana."""
    medidas: dict[str, list[dict]] = {}
    for ruta in rutas:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            medida = json.loads(linea)
            if "fila" in medida:
                medidas.setdefault(medida["fila"], []).append(medida)

    print(
        "| Fila | Librerías (s) | Primera llamada (s) | Mediana (ms) | p95 (ms) "
        "| Máximo (ms) | Propia (MiB) | Ficheros (MiB) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for nombre in FILAS:
        pasadas = medidas.get(nombre, [])
        if not pasadas:
            continue

        print(
            f"| {nombre} "
            f"| {_columna(pasadas, lambda medida: _segundos(medida['librerias_s']))} "
            f"| {_columna(pasadas, lambda medida: _segundos(medida['primera_llamada_s']))} "
            f"| {_columna(pasadas, lambda medida: _milisegundos(medida['mediana_s']))} "
            f"| {_columna(pasadas, lambda medida: _milisegundos(medida['p95_s']))} "
            f"| {_columna(pasadas, lambda medida: _milisegundos(medida['maximo_s']))} "
            f"| {_columna(pasadas, lambda medida: str(medida['memoria_al_terminar_mib']['RssAnon']))} "
            f"| {_columna(pasadas, lambda medida: str(medida['memoria_al_terminar_mib']['RssFile']))} |"
        )
    print()
    _tabla_de_medianas(medidas)


def main() -> None:
    parte, *argumentos = sys.argv[1:] or [""]
    if parte == "muestra":
        muestra(Path(argumentos[0]))
    elif parte == "filas":
        print(" ".join(FILAS))
    elif parte == "medir":
        asyncio.run(medir(argumentos[0], Path(argumentos[1])))
    elif parte == "resumen":
        resumen([Path(argumento) for argumento in argumentos])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
