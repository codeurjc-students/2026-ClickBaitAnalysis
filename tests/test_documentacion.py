"""Lo que las guías del repositorio tienen que decir de la configuración (#251).

`docs/ejecucion.md` lista cada ajuste de `settings` con su valor por defecto,
y una tabla así caduca sin avisar: #235 añadió dos claves, y #93, #159 y #230,
otros ajustes. Igual `.env.example`. Aquí se comprueba contra `Settings`, que
es la única fuente: si un campo nuevo no está en la guía, o la guía nombra uno
que ya no existe, falla.

Prueba el repositorio en sí, no un módulo, como `test_arquitectura.py` y
`test_compose.py`.
"""

import re
from pathlib import Path
from urllib.parse import unquote

from backend.config.settings import Settings

RAIZ = Path(__file__).resolve().parents[1]
EJECUCION = RAIZ / "docs" / "ejecucion.md"
ENV_EJEMPLO = RAIZ / ".env.example"

# Una variable de entorno escrita como código: `NLP_MODELS`, `HF_TOKEN`.
VARIABLE_EN_LA_GUIA = re.compile(r"`([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)`")


def _variables_de_settings() -> set[str]:
    # pydantic-settings lee cada campo de la variable con su nombre, sin
    # distinguir mayúsculas: `nlp_models` sale de `NLP_MODELS`.
    return {campo.upper() for campo in Settings.model_fields}


def test_la_guia_de_ejecucion_nombra_cada_ajuste():
    nombradas = set(VARIABLE_EN_LA_GUIA.findall(EJECUCION.read_text(encoding="utf-8")))

    assert sorted(_variables_de_settings() - nombradas) == []


def test_la_guia_de_ejecucion_no_nombra_ajustes_que_no_existen():
    nombradas = set(VARIABLE_EN_LA_GUIA.findall(EJECUCION.read_text(encoding="utf-8")))

    assert sorted(nombradas - _variables_de_settings()) == []


def test_env_example_solo_trae_ajustes_que_existen():
    variables = {
        linea.split("=", 1)[0].strip()
        for linea in ENV_EJEMPLO.read_text(encoding="utf-8").splitlines()
        if "=" in linea and not linea.lstrip().startswith("#")
    }

    assert variables, "no se leyó ninguna variable de .env.example"
    assert sorted(variables - _variables_de_settings()) == []


# --- Los enlaces de la documentación (#302) ---------------------------------
#
# Al pasar el README a `docs/diario.md` se reescribieron sus 130 enlaces
# relativos, y el README nuevo y los documentos de `docs/` enlazan entre sí y
# a secciones concretas. Un fichero que se renombra o un título que cambia
# dejan el enlace roto sin que nada falle: aquí se comprueba que cada enlace
# relativo lleva a un fichero que existe y, si lleva ancla, a un título que
# existe, con la regla con la que GitHub hace las anclas.

DOCUMENTOS = [RAIZ / "README.md", *sorted((RAIZ / "docs").rglob("*.md"))]
ENLACE = re.compile(r"\]\(([^)\s]+)\)")
EXTERNO = re.compile(r"(https?:|mailto:)")
CODIGO_EN_LINEA = re.compile(r"`[^`]*`")
TITULO = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _fuera_de_codigo(texto: str) -> list[str]:
    """Las líneas del texto que no están en un bloque de código."""
    lineas = []
    en_codigo = False
    for linea in texto.splitlines():
        if linea.lstrip().startswith("```"):
            en_codigo = not en_codigo
            continue
        if not en_codigo:
            lineas.append(linea)
    return lineas


def _enlaces(documento: Path) -> list[str]:
    texto = documento.read_text(encoding="utf-8")
    return [
        destino
        for linea in _fuera_de_codigo(texto)
        for destino in ENLACE.findall(CODIGO_EN_LINEA.sub("", linea))
        if not EXTERNO.match(destino)
    ]


def _ancla(titulo: str) -> str:
    """El ancla que GitHub da a un título: el texto que se ve, en minúsculas,
    sin signos (salvo el guion y el guion bajo) y con un guion por espacio."""
    texto = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", titulo)
    texto = texto.replace("`", "").replace("*", "").lower()
    texto = re.sub(r"[^\w\- ]", "", texto)
    return texto.replace(" ", "-")


def _anclas(documento: Path) -> set[str]:
    """Las anclas de los títulos de un documento, con el sufijo `-1`, `-2`…
    que GitHub añade a los repetidos."""
    vistas: dict[str, int] = {}
    anclas = set()
    for linea in _fuera_de_codigo(documento.read_text(encoding="utf-8")):
        titulo = TITULO.match(linea)
        if not titulo:
            continue
        base = _ancla(titulo.group(2))
        repeticiones = vistas.get(base, 0)
        anclas.add(base if repeticiones == 0 else f"{base}-{repeticiones}")
        vistas[base] = repeticiones + 1
    return anclas


def test_hay_enlaces_que_comprobar():
    # Que la expresión regular siga encontrando algo: sin esto, las dos de
    # abajo pasarían igual con una que no encontrara nada.
    assert sum(len(_enlaces(documento)) for documento in DOCUMENTOS) > 100


def test_cada_enlace_relativo_lleva_a_un_fichero_que_existe():
    rotos = [
        f"{documento.relative_to(RAIZ)}: {destino}"
        for documento in DOCUMENTOS
        for destino in _enlaces(documento)
        if not destino.startswith("#")
        and not (documento.parent / unquote(destino.partition("#")[0])).exists()
    ]

    assert rotos == []


def test_cada_ancla_lleva_a_un_titulo_que_existe():
    rotas = []
    for documento in DOCUMENTOS:
        for destino in _enlaces(documento):
            ruta, almohadilla, ancla = destino.partition("#")
            if not almohadilla:
                continue
            objetivo = (documento.parent / unquote(ruta)) if ruta else documento
            if objetivo.suffix != ".md" or not objetivo.is_file():
                continue
            if unquote(ancla) not in _anclas(objetivo):
                rotas.append(f"{documento.relative_to(RAIZ)}: {destino}")

    assert rotas == []
