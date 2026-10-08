"""#229 (2026-10-07) - ¿Qué hace la incoherencia con un cuerpo en otro idioma?

La puerta del idioma decide por el titular, pero la incoherencia compara el
titular con el cuerpo usando un modelo inglés. Este guion pasa tres titulares
ingleses, escritos a mano, por el detector de producción
(`get_incoherence_detector`, con su umbral y su recorte `_lead`) frente a tres
cuerpos de cada uno: el suyo en inglés, el mismo traducido al español y uno de
otro tema. Enseña lo que votaría la incoherencia sin la puerta del cuerpo, y lo
que dice `detectar` de cada cuerpo, que es con lo que la puerta decide.

Son tres ejemplos, no una medida: enseñan el mecanismo. Lo que sí se midió es
el detector sobre cuerpos, con `backend/evaluation/eval_idioma.py --cuerpos`.

Ejecutar desde la raíz: .venv/bin/python spikes/incoherencia_cuerpo_traducido.py
"""

import asyncio
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.core.idioma import detectar  # noqa: E402
from backend.integrations.nlp.factory import get_incoherence_detector  # noqa: E402

# Cada caso: el titular, su cuerpo en inglés, el mismo en español y otro tema.
CASOS = [
    (
        "Federal Reserve holds interest rates steady",
        "The Federal Reserve kept its benchmark interest rate unchanged on Wednesday, citing steady growth and easing inflation.",
        "La Reserva Federal mantuvo el miércoles sin cambios su tipo de interés de referencia, por el crecimiento estable y la inflación a la baja.",
        "A new species of frog was discovered in the rainforest of Ecuador by a team of biologists.",
    ),
    (
        "Spain wins the European Championship after beating England",
        "Spain beat England 2-1 in the final in Berlin to win a record fourth European Championship.",
        "España ganó a Inglaterra por 2-1 en la final de Berlín y conquistó su cuarta Eurocopa, un récord.",
        "The city council approved a new budget for public libraries and parks next year.",
    ),
    (
        "Wildfire forces thousands to evacuate in California",
        "A fast-moving wildfire in Northern California forced thousands of residents to leave their homes overnight.",
        "Un incendio forestal que avanza con rapidez en el norte de California obligó a miles de vecinos a dejar sus casas de madrugada.",
        "Scientists say a daily cup of coffee may be linked to a longer life.",
    ),
]
CUERPOS = ("inglés", "español", "otro tema")


def condiciones(detector) -> None:
    from huggingface_hub import snapshot_download

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    # El modelo se carga aquí, con el cargador del detector, para saber dónde
    # corre: en WSL, la GPU si la hay (producción corre en CPU).
    dispositivo = detector._get_model().device
    revision = Path(snapshot_download(detector.model_id, local_files_only=True)).name
    print(f"commit {commit}")
    print(
        f"{detector.model_id}, revisión {revision[:12]}, en {dispositivo} · "
        f"umbral {detector.threshold}"
    )
    print(
        f"sentence-transformers {version('sentence-transformers')} · "
        f"transformers {version('transformers')} · torch {version('torch')}"
    )


async def main() -> None:
    detector = get_incoherence_detector()
    condiciones(detector)
    print(f"\n{'titular':52} {'cuerpo':10} {'idioma':6} {'similitud':>9}  voto")
    for titular, *cuerpos in CASOS:
        for nombre, cuerpo in zip(CUERPOS, cuerpos, strict=True):
            datos = (await detector.detect(titular, cuerpo)).unwrap()
            voto = "incoherente" if datos["incoherent"] else "coherente"
            print(
                f"{titular[:52]:52} {nombre:10} {detectar(cuerpo):6} "
                f"{datos['similarity']:9.3f}  {voto}"
            )


if __name__ == "__main__":
    asyncio.run(main())
