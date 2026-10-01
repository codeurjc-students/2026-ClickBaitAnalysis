"""La ausencia escrita como texto, tratada como ausencia (#197).

Un modelo de lenguaje que rellena un parámetro opcional puede escribir su
ausencia en vez de omitirlo. El agente llamó a `analyze_headline` con
`content="None"` —la cadena, que es como Python escribe «nada»—, la herramienta
lo tomó como el cuerpo de la noticia, y la incoherencia comparó el titular con
esa palabra y dio un veredicto falso de engaño (A40, 2026-09-26).

`TextoOpcional` es un `str | None` que convierte en `None` lo que no es texto:
vacío, en blanco, o SÓLO «None» o «null» —las dos formas de escribir la
ausencia, la de Python y la de JSON—, sin distinguir mayúsculas. Todo lo demás
pasa intacto: «None of Us Knew» es un titular. No se añaden más palabras («N/A»,
«undefined») sin haberlas visto llegar.

Es un `BeforeValidator`: corrige lo que llega sin cambiar lo que se pide, así
que el esquema sigue siendo «texto o nada» en el contrato REST y en lo que lee
el modelo. Sirve igual en un modelo de Pydantic que en la firma de una
herramienta MCP, porque FastMCP la valida con Pydantic. Vive en `core/` porque
lo usan `analysis/` e `integrations/`, y no sabe nada del clickbait.
"""

from typing import Annotated

from pydantic import BeforeValidator

_AUSENCIA = {"", "none", "null"}


def es_ausente(valor: object) -> bool:
    """Si un valor es la ausencia de texto, aunque llegue escrito como texto."""
    return valor is None or (
        isinstance(valor, str) and valor.strip().casefold() in _AUSENCIA
    )


def _texto_o_nada(valor: object) -> object:
    return None if es_ausente(valor) else valor


TextoOpcional = Annotated[str | None, BeforeValidator(_texto_o_nada)]
