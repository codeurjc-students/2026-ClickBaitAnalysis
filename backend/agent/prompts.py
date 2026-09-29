"""Los prompts de sistema del agente, versionados en `prompts/` (R13.5, #188).

Son configuración y no código: un fichero por versión, que se lee tal cual y se
consulta desde la API (`GET /agent`, #189), para que se vea qué instrucciones
recibe el modelo. Cuál se usa lo decide quien monta el agente, con el ajuste
`llm_prompt` (#189); un prompt nuevo se añade también a su `Literal`, y un test
avisa si se olvida.

Salen de `spikes/prompts/` (#82) con UNA corrección: los dos llamaban
«zero-shot» a `detect_clickbait`, que dejó de serlo en #115. Es el error que
#183 corrigió en los docstrings de las tools, esta vez en el texto que el
modelo lee primero. Las copias del spike no se tocan: registran lo que se midió
con ellas.

`04-preciso` es el prompt de partida del spike; `03-estricto`, la alternativa.
Entre los dos no hay un ranking defendible (PR #176), e iterarlos es #192.

`05-llano` sale de #192: las respuestas de `04-preciso` eran fieles pero no se
entendían sin conocer el sistema, y la validación a mano señaló por qué —las
posiciones y los nombres internos, que el propio `04` exigía—. Cambia eso por un
glosario fijo, para que la traducción sea siempre la misma y se pueda juzgar, y
conserva las reglas de veracidad. Los decimales no los arregla el prompt: los
redondea el agente en lo que lee el modelo (`decimales_para_el_modelo`).
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
