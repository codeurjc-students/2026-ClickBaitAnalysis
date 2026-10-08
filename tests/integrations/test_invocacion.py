"""El modo de invocación de `detect_clickbait`, configurable (#159).

Desde #119 se podía cambiar QUÉ modelo ejecuta la señal, pero siempre se le
llamaba como clasificador y con las etiquetas de `Stremie`. Ahora la
configuración dice también CÓMO se le llama —clasificador o zero-shot— y qué
palabra del modelo corresponde a cada etiqueta del contrato.

Los casos de los mensajes de error se provocaron antes con los modelos reales
(`spikes/invocacion_casos.py`): un clasificador pedido como zero-shot no falla,
responde casi a cara o cruz; un modelo de inferencia (NLI) pedido como
clasificador responde «neutral».
"""

from typing import get_args

import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from backend.config.settings import (
    EtiquetaDeClickbait,
    ModeloConInvocacion,
    Settings,
    settings,
)
from backend.core.idioma import INGLES
from backend.core.models import ToolResult
from backend.integrations.nlp import dedicated, model_cards
from backend.integrations.nlp import tool as nlp_tool
from backend.integrations.nlp.factory import (
    ficha_efectiva,
    get_invocacion,
    get_model_id,
)
from backend.integrations.nlp.local import LocalNLPClient

_CLAVES = {"guardian_api_key": "x", "nyt_api_key": "x", "hf_token": "x"}

BART = "facebook/bart-large-mnli"
ZERO_SHOT_CON_PREGUNTA = {
    "id": BART,
    "task": "zero-shot-classification",
    "labels": {"sensationalist headline": "clickbait", "news report": "factual news"},
}
ELOZANO = {
    "id": "elozano/bert-base-cased-clickbait-news",
    "labels": {"Clickbait": "clickbait", "Normal": "factual news"},
}


class _Espia:
    """Un backend que anota cada llamada y responde lo que se le diga."""

    def __init__(self, etiqueta: str = "clickbait") -> None:
        self.etiqueta = etiqueta
        self.llamadas: list[tuple] = []

    async def classify(self, text, model):
        self.llamadas.append(("classify", model))
        return ToolResult.ok({"label": self.etiqueta, "score": 0.8})

    async def zero_shot(self, text, model, labels):
        self.llamadas.append(("zero_shot", model, labels))
        return ToolResult.ok({"label": self.etiqueta, "score": 0.7})


# --La señal


@pytest.mark.asyncio
async def test_como_zero_shot_pregunta_sus_etiquetas_y_traduce_la_que_gana():
    espia = _Espia("sensationalist headline")

    resultado = await dedicated.detect(
        espia,
        "10 Amazing Things",
        BART,
        dedicated.ZERO_SHOT,
        ZERO_SHOT_CON_PREGUNTA["labels"],
    )

    assert espia.llamadas == [
        ("zero_shot", BART, ["sensationalist headline", "news report"])
    ]
    assert resultado.unwrap() == {"label": "clickbait", "score": 0.7}


@pytest.mark.asyncio
async def test_sin_etiquetas_el_zero_shot_pregunta_las_del_contrato():
    """Las mismas con que E3-02 y #109 midieron a BART."""
    espia = _Espia("factual news")

    resultado = await dedicated.detect(espia, "Un titular", BART, dedicated.ZERO_SHOT)

    assert espia.llamadas == [("zero_shot", BART, ["clickbait", "factual news"])]
    assert resultado.unwrap()["label"] == "factual news"


@pytest.mark.asyncio
async def test_un_clasificador_con_otro_vocabulario_se_traduce():
    """El caso de #119: `elozano` dice «Normal» donde el dedicado dice «Not
    Clickbait», y con un titular clickbait no se notaba."""
    espia = _Espia("Normal")

    con_sus_etiquetas = await dedicated.detect(
        espia, "Un titular", ELOZANO["id"], etiquetas=ELOZANO["labels"]
    )
    sin_ellas = await dedicated.detect(espia, "Un titular", ELOZANO["id"])

    assert con_sus_etiquetas.unwrap()["label"] == "factual news"
    assert not sin_ellas.success
    assert "Normal" in (sin_ellas.error or "")


@pytest.mark.asyncio
async def test_un_nli_pedido_como_clasificador_dice_que_es_un_zero_shot():
    """Medido: BART como clasificador responde «neutral» a los dos titulares."""
    resultado = await dedicated.detect(_Espia("neutral"), "Un titular", BART)

    assert not resultado.success
    assert "zero-shot" in (resultado.error or "")


@pytest.mark.asyncio
async def test_un_clasificador_pedido_como_zero_shot_falla_en_vez_de_inventar(
    monkeypatch,
):
    """Medido: `transformers` sólo lo avisa en su log, y el dedicado así da
    0,506 a «factual news» con un titular clickbait. Se corta antes de llamar."""

    class _PipelineSinEntailment:
        entailment_id = -1
        llamado = False

        def __call__(self, *argumentos, **opciones):
            self.llamado = True
            return {"labels": ["clickbait"], "scores": [0.5]}

    pipeline = _PipelineSinEntailment()
    cliente = LocalNLPClient()
    monkeypatch.setattr(cliente, "_get_pipeline", lambda tarea, modelo: pipeline)

    resultado = await cliente.zero_shot(
        "Un titular", "Stremie/roberta-base-clickbait", ["clickbait", "factual news"]
    )

    assert not resultado.success
    assert "NLI" in (resultado.error or "")
    assert not pipeline.llamado


# --La configuración


def test_las_etiquetas_admitidas_son_las_del_contrato():
    """`settings` no puede importar la señal, así que la lista va en los dos
    sitios; este test es el que las ata."""
    assert (
        set(get_args(EtiquetaDeClickbait))
        == set(dedicated.ETIQUETAS.values())
        == set(dedicated.ETIQUETAS_ZERO_SHOT.values())
    )


def test_el_modo_se_lee_del_entorno_como_json(monkeypatch):
    monkeypatch.setenv(
        "NLP_MODELS",
        '{"detect_clickbait": {"id": "facebook/bart-large-mnli",'
        ' "task": "zero-shot-classification"},'
        ' "analyze_sentiment": "otro/tono"}',
    )

    modelos = Settings(**_CLAVES).nlp_models

    assert modelos["detect_clickbait"] == ModeloConInvocacion(
        id=BART, task="zero-shot-classification"
    )
    # La cadena de siempre sigue valiendo.
    assert modelos["analyze_sentiment"] == "otro/tono"


def test_el_modo_solo_vale_para_detect_clickbait():
    with pytest.raises(ValidationError):
        Settings(nlp_models={"analyze_sentiment": {"id": "otro/tono"}}, **_CLAVES)


@pytest.mark.parametrize(
    "etiquetas",
    [
        {"sensationalist headline": "clickbait"},  # falta «factual news»
        {"a": "clickbait", "b": "noticia"},  # «noticia» no es del contrato
    ],
)
def test_las_etiquetas_llevan_a_las_dos_del_contrato(etiquetas):
    """Si falta una, el modelo nunca podría darla."""
    with pytest.raises(ValidationError):
        Settings(
            nlp_models={"detect_clickbait": {"id": BART, "labels": etiquetas}},
            **_CLAVES,
        )


def test_sin_configurar_es_el_de_la_ficha_como_clasificador():
    invocacion = get_invocacion("detect_clickbait")

    assert invocacion.id == model_cards.model_id_de("detect_clickbait", INGLES)
    assert invocacion.task == "text-classification"
    assert invocacion.labels is None


def test_con_el_modo_configurado_el_id_sale_igual(monkeypatch):
    monkeypatch.setattr(
        settings,
        "nlp_models",
        {"detect_clickbait": ModeloConInvocacion(**ZERO_SHOT_CON_PREGUNTA)},
    )

    assert get_model_id("detect_clickbait") == BART
    assert get_invocacion("detect_clickbait").task == "zero-shot-classification"


# --Las dos fachadas


@pytest.mark.asyncio
async def test_las_dos_fachadas_llaman_como_dice_la_configuracion(monkeypatch):
    """Configurado DESPUÉS de importar y de registrar las herramientas: el modo
    se resuelve en cada llamada, como el id (#87)."""
    from backend.analysis import orchestrator

    monkeypatch.setattr(
        settings,
        "nlp_models",
        {"detect_clickbait": ModeloConInvocacion(**ZERO_SHOT_CON_PREGUNTA)},
    )
    esperada = ("zero_shot", BART, ["sensationalist headline", "news report"])

    espia_rest = _Espia("sensationalist headline")
    monkeypatch.setattr(orchestrator, "get_nlp_backend", lambda: espia_rest)
    senales = {senal.name: senal for senal in orchestrator._SIGNALS}
    resultado = await orchestrator._run_one(
        senales["detect_clickbait"], "Un titular", None
    )
    assert espia_rest.llamadas == [esperada]
    assert resultado.is_clickbait is True

    espia_mcp = _Espia("news report")
    monkeypatch.setattr(nlp_tool, "get_nlp_backend", lambda: espia_mcp)
    mcp = FastMCP("test")
    nlp_tool.register(mcp)
    await mcp.call_tool("detect_clickbait", {"headline": "Un titular"})
    assert espia_mcp.llamadas == [esperada]


# --La ficha


def test_la_ficha_de_un_zero_shot_publica_lo_que_se_le_pregunta(monkeypatch):
    """Las etiquetas de un zero-shot son la pregunta: con otras, el mismo modelo
    da otro resultado. Si no se publican, la ficha esconde la mitad del
    modelo."""
    monkeypatch.setattr(
        settings,
        "nlp_models",
        {"detect_clickbait": ModeloConInvocacion(**ZERO_SHOT_CON_PREGUNTA)},
    )

    ficha = ficha_efectiva("detect_clickbait")

    assert ficha["model_id"] == BART
    assert "zero-shot" in ficha["name"]
    assert "zero-shot" in ficha["task"]
    texto = " ".join(ficha["limitations"])
    assert "SIN EVALUAR" in texto
    assert "«sensationalist headline»" in texto
    assert "«news report»" in texto


def test_la_ficha_de_un_clasificador_con_otras_etiquetas_dice_la_traduccion(
    monkeypatch,
):
    monkeypatch.setattr(
        settings, "nlp_models", {"detect_clickbait": ModeloConInvocacion(**ELOZANO)}
    )

    texto = " ".join(ficha_efectiva("detect_clickbait")["limitations"])

    assert "«Normal» → factual news" in texto


def test_el_declarado_puesto_como_objeto_no_cambia_la_ficha(monkeypatch):
    """Poner el modelo que ya estaba, como clasificador y sin etiquetas, no es
    sustituirlo (como con la cadena, #119)."""
    declarada = model_cards.fichas_en(INGLES)["detect_clickbait"]
    monkeypatch.setattr(
        settings,
        "nlp_models",
        {"detect_clickbait": ModeloConInvocacion(id=declarada["model_id"])},
    )

    ficha = ficha_efectiva("detect_clickbait")

    assert ficha["model_id"] == declarada["model_id"]
    assert ficha["limitations"] == declarada["limitations"]
