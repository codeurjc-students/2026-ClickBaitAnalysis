"""Los ejemplos del formulario de Analizar dan lo que dicen sus etiquetas (#282).

El botón «caso ambiguo» rellenaba un titular que dejó de ser ambiguo el 25 de
agosto (#109), nueve días antes de que se creara el botón (#127), y nadie lo vio
hasta preparar la demostración: nada comprobaba que un ejemplo diera lo que
promete.

Comprobarlo del todo pide los modelos, y el CI no los carga. Por eso va en dos
mitades. `spikes/ejemplos_formulario.py` pasa cada botón por `analyze()` con los
modelos y graba lo que dio en `spikes/ejemplos_formulario/medida.json`. Aquí se
juzga sin ellos: el idioma, el léxico, el lineal y la regla del veredicto se
ejecutan DE VERDAD, porque no necesitan modelo, y de la medida se toma sólo lo
que respondieron los modelos opacos, la dedicada y el tono.

Falla pidiendo volver a medir cuando la medida deja de valer: si se cambia un
botón, o si la ficha de un modelo medido pasa a otro modelo o a otra revisión,
que es lo que pasó en #115. Y falla cuando lo que da el sistema ya no es lo que
promete la etiqueta.

Prueba el repositorio en sí, no un módulo, como `test_documentacion.py`.
"""

import json
import re
from pathlib import Path

import pytest

from backend.analysis import orchestrator
from backend.analysis.domain import AnalyzeRequest, OverallVerdict
from backend.config.settings import settings
from backend.core.idioma import ESPANOL, INGLES
from backend.core.models import ToolResult
from backend.integrations.nlp import dedicated
from backend.integrations.nlp.model_cards import ficha_declarada

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLA = RAIZ / "frontend" / "src" / "app" / "analisis" / "analisis-page.html"
MEDIDA = RAIZ / "spikes" / "ejemplos_formulario" / "medida.json"

# Un botón de ejemplo: `(click)="ejemplo('…')"` y, dentro, su etiqueta. Es la
# misma expresión que usa el guion, escrita aparte a propósito: si las dos
# lecturas de la plantilla divergieran, la primera prueba lo diría.
BOTON = re.compile(
    r"""\(click\)="ejemplo\('(?P<titular>(?:[^'\\]|\\.)*)'\)"\s*>"""
    r"""\s*(?P<etiqueta>[^<]+?)\s*</button>"""
)

# Lo que promete cada etiqueta. Vive sólo aquí: el guion mide, no juzga.
VEREDICTO_PROMETIDO = {
    "clickbait claro": OverallVerdict.STYLISTIC_CLICKBAIT,
    "titular factual": OverallVerdict.FACTUAL,
    "caso ambiguo": OverallVerdict.AMBIGUOUS,
}

# Este botón no promete un veredicto concreto: existe para enseñar que un
# titular en español se reconoce como tal y recibe alguno (#234).
EN_ESPANOL = "en español"

VOLVER_A_MEDIR = (
    "La medida grabada ya no vale. Lanza `.venv/bin/python "
    "spikes/ejemplos_formulario.py`, que carga los modelos, y commitea "
    "`spikes/ejemplos_formulario/medida.json`."
)

# La dedicada traduce la etiqueta del modelo a la del contrato, y la medida
# guarda la del contrato. Se deshace aquí para que el doble responda como el
# modelo y la traducción de verdad se ejecute.
ETIQUETA_DEL_MODELO = {
    del_contrato: del_modelo for del_modelo, del_contrato in dedicated.ETIQUETAS.items()
}


def _botones() -> list[tuple[str, str]]:
    """Etiqueta y titular de cada botón de ejemplo, en el orden de la plantilla."""
    return [
        (boton["etiqueta"], boton["titular"].replace("\\'", "'"))
        for boton in BOTON.finditer(PLANTILLA.read_text(encoding="utf-8"))
    ]


def _medida() -> dict:
    return json.loads(MEDIDA.read_text(encoding="utf-8"))


class _ModelosGrabados:
    """Backend NLP que responde lo que la medida grabó de cada modelo.

    Despacha por titular Y por modelo, como el de verdad: lo que se le pida de
    un modelo que no se midió no tiene respuesta, y se apunta en `sin_medida`
    en vez de inventarla.
    """

    def __init__(self, ejemplos: list[dict]) -> None:
        self._grabado: dict[tuple[str, str], tuple[str, dict]] = {}
        for ejemplo in ejemplos:
            analisis = ejemplo["analysis"]
            for senal in analisis["signals"]:
                if senal["status"] != "ok":
                    continue
                ficha = ficha_declarada(senal["name"], senal["data"]["language"])
                if ficha is None or ficha["model_id"] is None:
                    continue  # el léxico y el lineal se ejecutan de verdad
                clave = (analisis["headline"], ficha["model_id"])
                self._grabado[clave] = (senal["name"], senal["data"])
        self.sin_medida: list[tuple[str, str]] = []

    async def classify(self, text: str, model: str) -> ToolResult:
        if (text, model) not in self._grabado:
            self.sin_medida.append((text, model))
            return ToolResult.fail("no hay medida de este modelo")
        senal, datos = self._grabado[(text, model)]
        etiqueta = datos["label"]
        if senal == "detect_clickbait":
            etiqueta = ETIQUETA_DEL_MODELO[etiqueta]
        return ToolResult.ok({"label": etiqueta, "score": datos["score"]})

    async def zero_shot(self, text: str, model: str, labels: list[str]) -> ToolResult:
        # La medida es de las fichas, y ninguna llama así a su modelo.
        self.sin_medida.append((text, model))
        return ToolResult.fail("no hay medida de este modelo")


@pytest.fixture(autouse=True)
def _con_los_ajustes_de_las_fichas(monkeypatch):
    """Los modelos y umbrales de las fichas, diga lo que diga el `.env` de quien
    lanza la suite: son los que se midieron, y los que se sirven."""
    monkeypatch.setattr(settings, "nlp_models", {})
    monkeypatch.setattr(settings, "nlp_models_es", {})
    monkeypatch.setattr(settings, "nlp_thresholds", {})
    monkeypatch.setattr(settings, "nlp_thresholds_es", {})
    monkeypatch.setattr(settings, "nlp_linear_top_cues", None)


def test_cada_boton_de_ejemplo_tiene_su_promesa():
    # También es lo que impide que las demás pasen sin comprobar nada: si la
    # plantilla cambiara de forma y la expresión no encontrara los botones,
    # esto no daría las cuatro etiquetas.
    etiquetas = [etiqueta for etiqueta, _ in _botones()]

    assert sorted(etiquetas) == sorted([*VEREDICTO_PROMETIDO, EN_ESPANOL])


def test_los_botones_de_la_plantilla_son_los_que_se_midieron():
    medidos = [
        (ejemplo["label"], ejemplo["analysis"]["headline"])
        for ejemplo in _medida()["ejemplos"]
    ]

    assert _botones() == medidos, VOLVER_A_MEDIR


def test_la_medida_es_de_los_modelos_de_las_fichas():
    condiciones = _medida()["condiciones"]
    medidos = {
        (modelo["signal"], modelo["language"]): (modelo["model_id"], modelo["revision"])
        for modelo in condiciones["modelos"]
    }

    assert condiciones["ajustes"] == {}, VOLVER_A_MEDIR
    # Que no pase sin comparar nada: la dedicada, en los dos idiomas.
    assert {("detect_clickbait", INGLES), ("detect_clickbait", ESPANOL)} <= set(medidos)
    for (senal, idioma), medido in medidos.items():
        ficha = ficha_declarada(senal, idioma)
        assert ficha is not None, VOLVER_A_MEDIR
        assert (ficha["model_id"], ficha["revision"]) == medido, VOLVER_A_MEDIR


@pytest.mark.asyncio
@pytest.mark.parametrize("etiqueta", [*VEREDICTO_PROMETIDO, EN_ESPANOL])
async def test_cada_ejemplo_da_lo_que_promete_su_etiqueta(etiqueta, monkeypatch):
    ejemplos = _medida()["ejemplos"]
    grabado = next(
        (ejemplo["analysis"] for ejemplo in ejemplos if ejemplo["label"] == etiqueta),
        None,
    )
    assert grabado is not None, f"No hay medida de «{etiqueta}». {VOLVER_A_MEDIR}"
    modelos = _ModelosGrabados(ejemplos)
    monkeypatch.setattr(orchestrator, "get_nlp_backend", lambda: modelos)

    analisis = await orchestrator.analyze(AnalyzeRequest(headline=grabado["headline"]))

    assert modelos.sin_medida == [], VOLVER_A_MEDIR
    # Lo que aquí se ejecuta de verdad sigue votando como cuando se midió. Si
    # no, la medida describe otro sistema, aunque el veredicto coincidiera.
    votos = {senal.name: senal.is_clickbait for senal in analisis.signals}
    grabados = {senal["name"]: senal["is_clickbait"] for senal in grabado["signals"]}
    assert votos == grabados, VOLVER_A_MEDIR

    if etiqueta == EN_ESPANOL:
        assert analisis.language == ESPANOL
        assert analisis.verdict != OverallVerdict.NO_DATA
    else:
        assert analisis.verdict == VEREDICTO_PROMETIDO[etiqueta]
