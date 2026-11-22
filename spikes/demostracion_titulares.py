"""#214 (2026-11-12) - Los titulares de la demostración dan lo que dice su guion.

`docs/demostracion.md` cita el veredicto y las cifras de cada titular que se
enseña en la defensa. Son deterministas, pero cambian si cambia un modelo, un
umbral o la jerarquía del veredicto, y entonces el guion diría una cosa y la
pantalla otra, delante del tribunal. Aquí cada titular pasa por `analyze()`, el
camino de producción: se imprime lo que el guion cita, y el guion termina con
error si algún veredicto no es el esperado.

Comprueba además dos cosas que no dependen de ningún modelo: que cada titular y
cada cuerpo estén tal cual en el guion, para que este fichero y el guion no
puedan decir cosas distintas, y que los titulares de los pasos 2 y 3 sigan en el
formulario de Analizar, porque se introducen con sus botones de ejemplo, «caso
ambiguo» y «en español». Que cada botón dé lo que promete su etiqueta lo vigila
`tests/test_ejemplos_formulario.py` (#282).

El titular B es el de «caso ambiguo» desde que #282 lo cambió. Hasta entonces el
guion llevaba «Is the Federal Reserve About to Cut Interest Rates?», en el que
el lineal quedaba seis milésimas por encima de su umbral (0,356 con 0,35). El
veredicto no dependía de eso, como se creyó al escribirlo: a la forma le basta
un desacuerdo para quedar sin resolver, y la dedicada y el léxico ya
discrepaban. El margen del lineal se imprime igual, porque dice cuánto le falta
a esa señal para cambiar de voto, y el guion conserva un repuesto, el C.

Mide lo que se sirve, y no lo que haya ese día en el Hub de Hugging Face (desde
el 13 nov 2026; hasta entonces medía con red): `LocalNLPClient` pide cada
modelo por su nombre, sin revisión, y con red cargaría la última. Tres
condiciones las fija el propio guion, con las comprobaciones de
`spikes/ejemplos_formulario.py` (#282):

- CPU (`CUDA_VISIBLE_DEVICES` vacío): en WSL `transformers` usaría la GTX, y
  producción no tiene GPU. Si torch la ve igual, se para.
- Sin red (`HF_HUB_OFFLINE=1`), como la imagen: carga el `refs/main` de la
  caché, y al final se comprueba que es el commit que fija la ficha de cada
  modelo que respondió; si no lo es, se para. Una señal caída cuenta como
  fallo: sin red, es lo que pasa si falta un modelo en la caché, y el veredicto
  sin ella puede coincidir por casualidad con el de la guía.
- Los modelos y los umbrales de las fichas, que son los de producción: con
  `NLP_MODELS`, `NLP_THRESHOLDS` o los demás ajustes puestos, se para.

Ejecutar desde la raíz:

    .venv/bin/python spikes/demostracion_titulares.py

Resultados (2026-11-13, `dev` en `d007451`, torch 2.12.1 y transformers 5.12.0):
5 titulares, 0 fallos, y las mismas cifras que con red el 12 nov.

| Caso | Veredicto | Dedicada | Léxico | Lineal | Incoherencia | Tono |
|---|---|---|---|---|---|---|
| A | deceptive | clickbait 0,970 | 5 | 0,991 | 0,078 | neutral 0,758 |
| B | ambiguous | clickbait 0,859 | 0 | 0,760 | — | neutral 0,821 |
| C | ambiguous | factual news 0,971 | 0 | 0,036 | -0,055 | neutral 0,831 |
| Español | stylistic_clickbait | clickbait 0,994 | — | 0,429 | — | negative 0,514 |
| Asistente | stylistic_clickbait | clickbait 0,950 | 4 | 0,994 | — | negative 0,764 |

El léxico, en pistas; «—», la señal no se aplica. Los umbrales: el lineal, 0,35,
y la incoherencia, 0,3. En el titular del asistente, los tres rasgos que más
pesan en el lineal son «this» (+1,90), «you» (+1,75) y «what» (+1,14).

Los modelos, con la revisión de su ficha: `Stremie/roberta-base-clickbait`
(`517de05db9ba`), `ggcastle/beto-clickbait-es` (`03c31ac0c288`),
`cardiffnlp/twitter-roberta-base-sentiment-latest` (`3216a57f2a0d`),
`lxyuan/distilbert-base-multilingual-cased-sentiments-student`
(`cf991100d706`) y `sentence-transformers/all-MiniLM-L6-v2` (`1110a243fdf4`).
"""

import asyncio
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog

# Antes de importar nada de `backend`: torch y `huggingface_hub` las leen al
# importarse. Son las condiciones de `ejemplos_formulario.py` (#282).
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.analysis.domain import AnalyzeRequest, SignalResult  # noqa: E402
from backend.analysis.orchestrator import analyze  # noqa: E402

# Las comprobaciones de que lo medido es lo que se sirve: una sola regla para
# los dos guiones que pasan titulares por `analyze()`.
from spikes.ejemplos_formulario import (  # noqa: E402
    ajustes_puestos,
    modelos_que_respondieron,
)

# Sólo avisos: lo que interesa es lo que se imprime aquí.
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
)

GUION = RAIZ / "docs" / "demostracion.md"
FORMULARIO = RAIZ / "frontend" / "src" / "app" / "analisis" / "analisis-page.html"

TITULAR_AMBIGUO = "The Federal Reserve Just Held Interest Rates Steady. Here's Why"
TITULAR_EN_ESPANOL = "No vas a creer lo que hizo este perro al ver a su dueño"

# Los titulares que el guion introduce con un botón de ejemplo del formulario.
BOTONES = {"caso ambiguo": TITULAR_AMBIGUO, "en español": TITULAR_EN_ESPANOL}


@dataclass(frozen=True)
class Caso:
    """Un titular del guion, con el veredicto que el guion dice que da."""

    paso: str
    titular: str
    cuerpo: str | None
    veredicto: str


CASOS = [
    Caso(
        "paso 1, titular A",
        "10 Secrets Doctors Won't Tell You... Are You Ready?",
        "A small study in mice found modest effects of the diet after eight weeks.",
        "deceptive",
    ),
    Caso("paso 2, titular B", TITULAR_AMBIGUO, None, "ambiguous"),
    Caso(
        "paso 2, el repuesto: titular C",
        "Federal Reserve raises interest rates by a quarter point",
        "The local football team won the championship after a dramatic penalty "
        "shootout on Sunday night.",
        "ambiguous",
    ),
    Caso("paso 3, en español", TITULAR_EN_ESPANOL, None, "stylistic_clickbait"),
    Caso(
        "paso 6, el del asistente",
        "You Won't Believe What This Dog Did Next",
        None,
        "stylistic_clickbait",
    ),
]


def resumen(senal: SignalResult) -> str:
    """Lo que el guion cita de una señal, en una línea."""
    if senal.status.value != "ok" or senal.data is None:
        return f"{senal.status.value} · {senal.detail}"
    datos = senal.data
    if senal.name == "detect_clickbait_lexical":
        pistas = [pista["cue"] for pista in datos["matches"]]
        return f"{datos['score']} pistas {pistas} · umbral {datos['threshold']}"
    if senal.name == "detect_clickbait_linear":
        margen = datos["probability"] - datos["threshold"]
        pesos = ", ".join(
            f"{rasgo} {peso:+.2f}" for rasgo, peso in datos["top_cues"][:3]
        )
        return (
            f"probabilidad {datos['probability']:.3f} · umbral {datos['threshold']} "
            f"(margen {margen:+.3f}) · {pesos}"
        )
    if senal.name == "detect_clickbait_incoherence":
        return f"similitud {datos['similarity']:.3f} · umbral {datos['threshold']}"
    return f"{datos['label']} {datos['score']:.3f}"


def cabecera() -> str:
    """Cuándo y sobre qué commit se mide, para poder citar la salida."""
    ahora = datetime.now().astimezone().isoformat(timespec="seconds")
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=RAIZ,
    ).stdout.strip()
    sucio = subprocess.run(
        ["git", "diff", "--quiet", "HEAD"], check=False, cwd=RAIZ
    ).returncode
    aviso = " (con cambios sin commitear)" if sucio else ""
    import torch
    import transformers

    if torch.cuda.is_available():
        raise SystemExit("torch ve una GPU: la medida tiene que ser en CPU")
    return (
        f"== {ahora} · {commit}{aviso} · CPU y sin red · "
        f"torch {torch.__version__} · transformers {transformers.__version__}"
    )


def textos_fuera_del_guion() -> list[str]:
    """Los titulares y cuerpos de `CASOS` que el guion no trae tal cual."""
    guion = GUION.read_text(encoding="utf-8")
    textos = [texto for caso in CASOS for texto in (caso.titular, caso.cuerpo) if texto]
    return [texto for texto in textos if texto not in guion]


def botones_cambiados() -> list[str]:
    """Las etiquetas de `BOTONES` cuyo titular ya no está en el formulario."""
    formulario = FORMULARIO.read_text(encoding="utf-8")
    # En la plantilla el titular va entre comillas simples, con las suyas escapadas.
    return [
        etiqueta
        for etiqueta, titular in BOTONES.items()
        if titular.replace("'", "\\'") not in formulario
    ]


async def comprobar() -> int:
    """Analiza cada caso y devuelve cuántas comprobaciones fallan."""
    puestos = ajustes_puestos()
    if puestos:
        raise SystemExit(
            f"con {sorted(puestos)} puestos no se mide lo que se sirve: la guía "
            "cita los modelos y los umbrales de las fichas"
        )
    print(cabecera())
    fallos = 0

    for texto in textos_fuera_del_guion():
        print(f"\n!! no está en {GUION.name}: «{texto}»")
        fallos += 1
    for etiqueta in botones_cambiados():
        print(
            f"\n!! el ejemplo «{etiqueta}» de {FORMULARIO.name} ya no es el del guion"
        )
        fallos += 1

    todos = []
    for caso in CASOS:
        analisis = await analyze(
            AnalyzeRequest(headline=caso.titular, content=caso.cuerpo)
        )
        todos.append(analisis.model_dump(mode="json"))
        veredicto = analisis.verdict.value
        acierta = veredicto == caso.veredicto
        fallos += 0 if acierta else 1
        marca = "ok" if acierta else f"!! el guion dice {caso.veredicto}"
        cuerpo = "con cuerpo" if caso.cuerpo else "sin cuerpo"
        print(f"\n== {caso.paso} · «{caso.titular}» ({cuerpo})")
        print(f"   veredicto {veredicto} · idioma {analisis.language} · {marca}")
        for senal in analisis.signals:
            print(f"   {senal.name:30} {resumen(senal)}")
            # Sin red, un modelo que no está en la caché falla, y el veredicto
            # se calcula sin su señal: podría coincidir con el de la guía por
            # casualidad.
            if senal.status.value == "error":
                print("   !! una señal caída no vota: el veredicto no es el servido")
                fallos += 1

    # Se para si en la caché no está la revisión de la ficha.
    print("\n== los modelos que respondieron, con la revisión de su ficha")
    for modelo in modelos_que_respondieron(todos):
        print(
            f"   {modelo['language']} · {modelo['signal']:30} "
            f"{modelo['model_id']} · {modelo['revision'][:12]}"
        )

    print(f"\n== {len(CASOS)} titulares · {fallos} fallos")
    return fallos


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(comprobar()) else 0)
