"""#282 (2026-11-12) - ¿Da cada ejemplo del formulario lo que dice su etiqueta?

El formulario de Analizar trae cuatro botones de ejemplo, y el etiquetado «caso
ambiguo» rellenaba un titular que dejó de ser ambiguo el 25 de agosto (#109),
nueve días antes de que existiera el botón (#127): nada lo comprobaba. Este
guion es la mitad que necesita los modelos; la que juzga es
`tests/test_ejemplos_formulario.py`, que corre en el CI sin ellos.

Sin argumentos, lee los botones de la plantilla, pasa cada titular por
`analyze()` —sin cuerpo, como hace el botón— y graba en
`spikes/ejemplos_formulario/medida.json` el análisis entero de cada uno, con el
id y la revisión de cada modelo que respondió. La prueba toma de ahí lo que
dieron los modelos opacos y ejecuta lo demás de verdad. **Se vuelve a lanzar al
cambiar un botón, un modelo o su revisión**: la prueba falla hasta entonces.

Con `--candidatos <fichero>` mide una lista cualquiera, un titular por línea, y
graba una fila por titular al lado (`<fichero>.json`, o donde diga `--salida`):
así se eligió el sustituto.

Tres condiciones las fija el propio guion, porque también son de la medida:

- CPU (`CUDA_VISIBLE_DEVICES` vacío): en WSL `transformers` usaría la GTX, y
  producción no tiene GPU.
- Sin red (`HF_HUB_OFFLINE=1`): `LocalNLPClient` pide cada modelo por su
  nombre, sin revisión, y con red cargaría lo que haya hoy en el Hub. Sin ella
  carga el `refs/main` de la caché, y se comprueba que es el commit que fija
  la ficha; si no lo es, se para.
- Los modelos y los umbrales de las fichas: con `NLP_MODELS`, `NLP_THRESHOLDS`
  o los demás ajustes puestos no graba la medida, sólo mide candidatos, y lo
  anota.

Ejecutar desde la raíz:

    .venv/bin/python spikes/ejemplos_formulario.py
    .venv/bin/python spikes/ejemplos_formulario.py --candidatos spikes/ejemplos_formulario/candidatos.txt

Resultados (2026-11-12, `dev` en `15ae202`, torch 2.12.1 y transformers 5.12.0).
La cifra de la dedicada es la de la etiqueta que da; el corte del lineal, 0,35.

| Etiqueta | Titular | Veredicto | Dedicada | Léxico | Lineal |
|---|---|---|---|---|---|
| clickbait claro | `10 Amazing Things You Won't Believe` | `stylistic_clickbait` | sí, «clickbait» 0,967 | sí, 4 pistas | sí, 0,997 |
| titular factual | `Federal Reserve Holds Interest Rates Steady` | `factual` | no, «factual news» 0,968 | no, 0 pistas | no, 0,086 |
| caso ambiguo | `The Federal Reserve Just Held Interest Rates Steady. Here's Why` | `ambiguous` | sí, «clickbait» 0,859 | no, 0 pistas | sí, 0,760 |
| en español | `No vas a creer lo que hizo este perro al ver a su dueño` | `stylistic_clickbait` | sí, «clickbait» 0,994 | no aplica | sí, 0,429 |

Los 72 candidatos (`candidatos.txt`): 36 `ambiguous`, 30 `stylistic_clickbait`
y 6 `factual`.

El titular que había en el botón, `17 Things Nobody Tells You About Moving
Abroad` (`titular_anterior.txt`): `stylistic_clickbait` con los modelos de hoy
(«clickbait» 0,957, 4 pistas y 0,985), y `ambiguous` con el zero-shot que
votaba hasta #109 («factual news» 0,656, con el léxico y el lineal igual).
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

# Antes de importar nada de `backend`: torch y `huggingface_hub` las leen al
# importarse.
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

PLANTILLA = RAIZ / "frontend" / "src" / "app" / "analisis" / "analisis-page.html"
MEDIDA = RAIZ / "spikes" / "ejemplos_formulario" / "medida.json"

# Un botón de ejemplo: `(click)="ejemplo('…')"` y, dentro, su etiqueta. El
# titular va entre comillas simples, con las suyas escapadas (`\'`).
BOTON = re.compile(
    r"""\(click\)="ejemplo\('(?P<titular>(?:[^'\\]|\\.)*)'\)"\s*>"""
    r"""\s*(?P<etiqueta>[^<]+?)\s*</button>"""
)

# Lo que cambia qué modelo responde o con qué umbral decide.
AJUSTES = (
    "nlp_models",
    "nlp_models_es",
    "nlp_thresholds",
    "nlp_thresholds_es",
    "nlp_linear_top_cues",
)

VOTO = {True: "sí", False: "no", None: "no vota"}


def leer_ejemplos() -> list[dict[str, str]]:
    """Etiqueta y titular de cada botón de ejemplo, en el orden de la plantilla."""
    ejemplos = [
        {"label": boton["etiqueta"], "headline": boton["titular"].replace("\\'", "'")}
        for boton in BOTON.finditer(PLANTILLA.read_text(encoding="utf-8"))
    ]
    if not ejemplos:
        raise SystemExit(f"ningún botón de ejemplo en {PLANTILLA}")
    return ejemplos


def leer_candidatos(fichero: Path) -> list[str]:
    """Un titular por línea; las vacías y las que empiezan por `#`, fuera."""
    lineas = fichero.read_text(encoding="utf-8").splitlines()
    return [
        linea.strip()
        for linea in lineas
        if linea.strip() and not linea.lstrip().startswith("#")
    ]


def ajustes_puestos() -> dict:
    """Los ajustes que apartan la medida de las fichas, con su valor."""
    from backend.config.settings import settings

    puestos = {
        nombre.upper(): valor
        for nombre, valor in settings.model_dump(
            include=set(AJUSTES), mode="json"
        ).items()
        if valor
    }
    if settings.nlp_backend != "local":
        puestos["NLP_BACKEND"] = settings.nlp_backend
    return puestos


async def analizar(titulares: list[str]) -> list[dict]:
    """El análisis de cada titular, sin cuerpo, como lo devuelve la API."""
    from backend.analysis.domain import AnalyzeRequest
    from backend.analysis.orchestrator import analyze

    analisis = []
    for titular in titulares:
        respuesta = await analyze(AnalyzeRequest(headline=titular))
        analisis.append(respuesta.model_dump(mode="json"))

    # Una señal caída no vota, y el veredicto se calcularía sin ella: esa
    # medida no es la del sistema.
    caidas = [
        f"{senal['name']} en «{uno['headline']}»: {senal['detail']}"
        for uno in analisis
        for senal in uno["signals"]
        if senal["status"] == "error"
    ]
    if caidas:
        raise SystemExit("señales que fallaron:\n  " + "\n  ".join(caidas))
    return analisis


def modelos_que_respondieron(analisis: list[dict]) -> list[dict]:
    """El id y la revisión de cada modelo que dio una señal.

    La revisión es la que hay en la caché, que es la que se cargó, y tiene que
    ser la de la ficha: si no, lo medido no es lo que se sirve.
    """
    from huggingface_hub import constants

    from backend.integrations.nlp.model_cards import ficha_declarada

    respondieron = sorted(
        {
            (senal["name"], senal["data"]["language"])
            for uno in analisis
            for senal in uno["signals"]
            if senal["status"] == "ok"
        }
    )
    modelos = []
    for nombre, idioma in respondieron:
        ficha = ficha_declarada(nombre, idioma)
        if ficha is None or ficha["model_id"] is None:
            continue  # el léxico y el lineal no tienen nada que descargar
        referencia = (
            Path(constants.HF_HUB_CACHE)
            / ("models--" + ficha["model_id"].replace("/", "--"))
            / "refs"
            / "main"
        )
        en_cache = referencia.read_text(encoding="utf-8").strip()
        if en_cache != ficha["revision"]:
            raise SystemExit(
                f"{ficha['model_id']}: en la caché está {en_cache[:12]} y la ficha "
                f"fija {str(ficha['revision'])[:12]}. Lo medido no es lo que se sirve."
            )
        modelos.append(
            {
                "signal": nombre,
                "language": idioma,
                "model_id": ficha["model_id"],
                "revision": en_cache,
            }
        )
    return modelos


def _git(*argumentos: str) -> str | None:
    """La salida de una orden de git, o `None` si aquí no hay repositorio."""
    orden = subprocess.run(
        ["git", *argumentos], cwd=RAIZ, capture_output=True, text=True, check=False
    )
    return orden.stdout.strip() if orden.returncode == 0 else None


def condiciones(analisis: list[dict], puestos: dict) -> dict:
    """Con qué se midió: el código, las versiones, el dispositivo y los modelos."""
    import torch
    import transformers

    if torch.cuda.is_available():
        raise SystemExit("torch ve una GPU: la medida tiene que ser en CPU")
    return {
        "fecha": datetime.now(UTC).date().isoformat(),
        "commit": _git("rev-parse", "--short", "HEAD"),
        # Lo que se mide es `backend/`: si tiene cambios sin commitear, el
        # commit de arriba no lo describe.
        "backend_con_cambios": bool(_git("status", "--short", "--", "backend")),
        "dispositivo": "cpu",
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "ajustes": puestos,
        # Con ajustes puestos, quien respondió no es el modelo de la ficha.
        "modelos": [] if puestos else modelos_que_respondieron(analisis),
    }


def resumen(uno: dict) -> dict:
    """Lo que decide el veredicto de un análisis: el voto y la cifra de cada
    señal de forma, y las pistas del léxico."""
    senales = {senal["name"]: senal for senal in uno["signals"]}

    def de(nombre: str, *campos: str) -> dict:
        senal = senales[nombre]
        datos = senal["data"] or {}
        return {
            "status": senal["status"],
            "is_clickbait": senal["is_clickbait"],
            **{campo: datos.get(campo) for campo in campos},
        }

    lexico = de("detect_clickbait_lexical", "score")
    lexico["cues"] = [
        pista["cue"]
        for pista in (senales["detect_clickbait_lexical"]["data"] or {}).get(
            "matches", []
        )
    ]
    return {
        "headline": uno["headline"],
        "language": uno["language"],
        "verdict": uno["verdict"],
        "dedicated": de("detect_clickbait", "label", "score"),
        "lexical": lexico,
        "linear": de("detect_clickbait_linear", "probability", "threshold"),
    }


def _celda(senal: dict, cifra: str) -> str:
    """El voto de una señal y su cifra, o que no se aplicó."""
    if senal["status"] != "ok":
        return "no aplica"
    return f"{VOTO[senal['is_clickbait']]}, {cifra}"


def fila(uno: dict) -> str:
    """Una fila de la tabla: el titular, su veredicto y lo que dio cada señal."""
    corto = resumen(uno)
    dedicada, lexico, lineal = corto["dedicated"], corto["lexical"], corto["linear"]
    pistas = f" ({', '.join(lexico['cues'])})" if lexico["cues"] else ""
    celdas = [
        f"`{corto['headline']}`",
        f"`{corto['verdict']}`",
        _celda(dedicada, f"«{dedicada['label']}» {dedicada['score'] or 0:.3f}"),
        _celda(lexico, f"{lexico['score']} pistas{pistas}"),
        _celda(lineal, f"{lineal['probability'] or 0:.3f}"),
    ]
    return "| " + " | ".join(celdas) + " |"


def escribir(fichero: Path, contenido: dict) -> None:
    """Graba el JSON con finales de línea de Unix, se lance desde donde se lance."""
    fichero.parent.mkdir(exist_ok=True)
    fichero.write_text(
        json.dumps(contenido, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"\ngrabado en {fichero}")


def main() -> None:
    argumentos = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    argumentos.add_argument(
        "--candidatos",
        type=Path,
        help="mide los titulares de este fichero, uno por línea, en vez de los botones",
    )
    argumentos.add_argument(
        "--salida",
        type=Path,
        help="dónde grabar lo de --candidatos (por defecto, <fichero>.json)",
    )
    opciones = argumentos.parse_args()
    candidatos = opciones.candidatos
    if opciones.salida and candidatos is None:
        argumentos.error("--salida sólo va con --candidatos: la medida tiene su sitio")
    puestos = ajustes_puestos()

    if candidatos is None:
        if puestos:
            raise SystemExit(
                f"con {sorted(puestos)} puestos no se graba la medida: la que juzga "
                "la prueba es la de los modelos y umbrales de las fichas"
            )
        ejemplos = leer_ejemplos()
        analisis = asyncio.run(analizar([ejemplo["headline"] for ejemplo in ejemplos]))
        medida = condiciones(analisis, puestos)
        print("| Etiqueta | Titular | Veredicto | Dedicada | Léxico | Lineal (0,35) |")
        print("|---|---|---|---|---|---|")
        for ejemplo, uno in zip(ejemplos, analisis, strict=True):
            print(f"| {ejemplo['label']} {fila(uno)}")
        escribir(
            MEDIDA,
            {
                "condiciones": medida,
                "ejemplos": [
                    {"label": ejemplo["label"], "analysis": uno}
                    for ejemplo, uno in zip(ejemplos, analisis, strict=True)
                ],
            },
        )
    else:
        analisis = asyncio.run(analizar(leer_candidatos(candidatos)))
        medida = condiciones(analisis, puestos)
        print("| Titular | Veredicto | Dedicada | Léxico | Lineal (0,35) |")
        print("|---|---|---|---|---|")
        for uno in analisis:
            print(fila(uno))
        veredictos = Counter(uno["verdict"] for uno in analisis)
        print(f"\n{len(analisis)} titulares: {dict(veredictos.most_common())}")
        escribir(
            opciones.salida or candidatos.with_suffix(".json"),
            {"condiciones": medida, "titulares": [resumen(uno) for uno in analisis]},
        )

    print(f"condiciones: {json.dumps(medida, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
