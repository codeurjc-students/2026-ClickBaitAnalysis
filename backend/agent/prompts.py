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
redondea el agente en lo que lee el modelo (`decimales_para_el_modelo`). Fue el
de por defecto de #192 a #269, junto con el muestreo preciso (`llm_temperature`),
que es con lo que ganó la comparación. Desde #234 su párrafo de límites dice
que las herramientas analizan inglés y español, y cuáles no se aplican en
español: decía «entrenadas con titulares en inglés», falso desde `v0.8`. Se
corrigió en su sitio, y el texto de antes queda en la parte `cierre` de
`spikes/agente_a40.py`, que mide los dos.

`06-dato` sale de #269: es `05-llano` más un párrafo en «Noticias», que dice
que el texto de una noticia es un dato y no una orden. Con `05-llano`, el 27B
repitió el veredicto que le dictaba una noticia (2 de 4) y copió un enlace
inyectado (1 de 4), aunque el prompt ya decía «No copies enlaces». Que no
diverjan en nada más lo comprueba `tests/agent/test_prompts.py`: si no, al
compararlos no se sabría a qué atribuir la diferencia. Es el de por defecto
desde #269: con las 26 consultas cumplió la regla de #78 (98/104 frente a
99/104, intercalados en la misma sesión). Que reduzca la inyección no se
puede afirmar: en otra sesión, 0 obediencias de 16 frente a 1 de 16 con
`05-llano`, y la regla publicada pedía al menos 2 con éste.
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
