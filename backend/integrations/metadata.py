"""Metadata declarada en cada tool MCP, para el catálogo.

El objeto ``Tool`` del protocolo trae nombre, descripción y esquema, pero **no
categoría ni procedencia**. MCP permite adjuntar un ``meta`` libre por tool, y
eso viaja intacto hasta el cliente, así que la información se declara en el
origen en vez de en un mapa cableado en la API — que obligaría a editar la API
cada vez que se añade una fuente.

**Dos ejes, y se tratan distinto a propósito.**

La **categoría** es un juicio: qué tipo de trabajo hace la herramienta. No se
puede derivar de dónde vive el fichero — ``describe_models`` está en ``nlp/``
pero es una utilidad, no una señal de análisis. Así que se declara, y declararla
obliga a pensarla al añadir la siguiente.

La **integración** es un hecho de ubicación: de qué paquete viene. Se deriva del
módulo, y por eso **no puede mentir**. Declararla a mano permitiría que el
paquete dijera una cosa y el ``meta`` otra, en silencio — el mismo fallo que el
campo ``signal`` de las fichas de modelo.
"""

from typing import Any, Literal

# Cerradas a propósito: si hiciera falta una cuarta, es una decisión, no un
# descuido de quien añade una tool.
#
#
# Efecto secundario útil: «Señales de análisis» son exactamente las que llevan
# ficha de modelo, así que la categoría predice si `model_card` viene o no.
Categoria = Literal["Fuentes de contenido", "Señales de análisis", "Utilidades"]

# Prefijo de los paquetes de integración, para recortarlo al derivar el origen.
_PREFIJO = "backend.integrations."


def tool_meta(categoria: Categoria, modulo: str) -> dict[str, Any]:
    """Construye el ``meta`` de una tool. Se usa como ``@mcp.tool(meta=...)``.

    ``modulo`` es siempre ``__name__``: de ahí sale la integración. Para una
    herramienta del núcleo —fuera de ``backend/integrations/``— la integración
    es ``None``, que significa «no envuelve ninguna fuente externa».

    >>> tool_meta("Señales de análisis", "backend.integrations.nlp.tool")
    {'category': 'Señales de análisis', 'integration': 'nlp'}
    """
    return {"category": categoria, "integration": _integracion_de(modulo)}


def _integracion_de(modulo: str) -> str | None:
    """Saca el nombre del paquete de integración de un módulo, o None."""
    if not modulo.startswith(_PREFIJO):
        return None
    return modulo[len(_PREFIJO) :].split(".", 1)[0]
    # Recorta el prefijo y coge la primera parte, que es el paquete de integración.
