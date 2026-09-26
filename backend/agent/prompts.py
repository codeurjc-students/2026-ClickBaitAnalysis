"""Los prompts de sistema del agente, versionados en `prompts/` (R13.5, #188).

Son configuración y no código: un fichero por versión, que se lee tal cual y se
podrá consultar desde la API (#189), para que se vea qué instrucciones recibe el
modelo. Cuál se usa lo decide quien monta el agente, y el ajuste que lo elige
llega con #189, que es quien lo va a leer.

Salen de `spikes/prompts/` (#82) con UNA corrección: los dos llamaban
«zero-shot» a `detect_clickbait`, que dejó de serlo en #115. Es el error que
#183 corrigió en los docstrings de las tools, esta vez en el texto que el
modelo lee primero. Las copias del spike no se tocan: registran lo que se midió
con ellas.

`04-preciso` es el prompt de partida del spike; `03-estricto`, la alternativa.
Entre los dos no hay un ranking defendible (PR #176), e iterarlos es #192.
"""

from pathlib import Path

CARPETA = Path(__file__).resolve().parent / "prompts"


def disponibles() -> list[str]:
    """Los nombres de los prompts versionados, sin la extensión."""
    return sorted(fichero.stem for fichero in CARPETA.glob("*.md"))


def cargar(nombre: str) -> str:
    """El texto de un prompt, tal cual está en su fichero."""
    if nombre not in disponibles():
        raise ValueError(
            f"No hay ningún prompt llamado «{nombre}». "
            f"Disponibles: {', '.join(disponibles())}."
        )
    return (CARPETA / f"{nombre}.md").read_text(encoding="utf-8")
