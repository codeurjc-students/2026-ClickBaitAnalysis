"""Descubrimiento y registro automático de integraciones (R1.9).

Aquí se recorre ``backend/integrations/``, se importa el ``tool`` de cada
paquete y se llama a su ``register(mcp)``. Añadir una integración pasa a ser
crear el paquete; nadie toca ``main.py``.

Un paquete **sin módulo ``tool``** no es un fallo: es una integración que el
sistema consume por dentro y no publica herramientas. El primero es ``llm/``,
que usa el agente (#187). Se anota aparte, en ``without_tools``, porque lo que
cae en ``failed`` se anuncia al arrancar como integración rota.
"""

import importlib
import importlib.util
import pkgutil
from dataclasses import dataclass, field

import structlog
from mcp.server.fastmcp import FastMCP

log = structlog.get_logger()

# Módulo que se espera dentro de cada paquete de integración.
MODULO_TOOL = "tool"


@dataclass(frozen=True)  # Inmutable
class DiscoveryResult:
    """Qué se registró y qué falló al intentarlo."""

    registered: tuple[str, ...] = ()
    failed: dict[str, str] = field(default_factory=dict)  # paquete -> motivo
    # Integraciones sin módulo `tool`: existen, pero no publican herramientas.
    without_tools: tuple[str, ...] = ()

    # field y default factory para inmutabilidad y no compartir entre instancias.

    # Ej failed: "weather_api": "ImportError: No module named 'requests'"

    @property
    def degraded(self) -> bool:
        return bool(self.failed)


def discover_and_register(mcp: FastMCP) -> DiscoveryResult:
    """Registra en ``mcp`` todas las integraciones que expongan ``register``.

    Un fallo al importar una integración **no tumba el servidor**: se anota y se
    sigue con las demás, para que un paquete roto no deje al sistema sin las
    otras diez herramientas. Es la misma postura que en ``/analyze`` con las
    señales.
    """
    if __package__ is None:
        raise RuntimeError("El descubrimiento sólo funciona dentro de un paquete.")

    paquete = importlib.import_module(__package__)
    registrados: list[str] = []
    fallidos: dict[str, str] = {}
    sin_herramientas: list[str] = []

    # Orden alfabético, no el del sistema de ficheros: el catálogo y los tests
    # dependen de que sea siempre el mismo.
    nombres = sorted(
        nombre
        for _, nombre, es_paquete in pkgutil.iter_modules(paquete.__path__)
        if es_paquete
    )

    for nombre in nombres:
        ruta_tool = f"{__package__}.{nombre}.{MODULO_TOOL}"
        try:
            # `find_spec` pregunta si el módulo existe sin ejecutarlo (sí importa
            # el paquete que lo contiene). Distingue «no tiene `tool`», que no es
            # un fallo, de «tiene `tool` y no carga», que sí lo es.
            tiene_tool = importlib.util.find_spec(ruta_tool) is not None
        except ImportError as exc:  # el propio paquete no se puede importar
            fallidos[nombre] = f"{type(exc).__name__}: {exc}"
            log.warning("integracion.omitida", integracion=nombre, motivo=str(exc))
            continue
        if not tiene_tool:
            sin_herramientas.append(nombre)
            continue

        try:
            modulo = importlib.import_module(ruta_tool)
            registrar = modulo.register
        except (ImportError, AttributeError) as exc:
            # Sin `tool.register` no es una integración registrable: puede ser un
            # paquete de apoyo. Se anota por si es un error, pero no se levanta.
            fallidos[nombre] = f"{type(exc).__name__}: {exc}"
            log.warning("integracion.omitida", integracion=nombre, motivo=str(exc))
            continue

        try:
            registrar(mcp)
        except Exception as exc:
            fallidos[nombre] = f"{type(exc).__name__}: {exc}"
            log.error("integracion.fallo", integracion=nombre, motivo=str(exc))
            continue  # Saltamos, no se detiene

        registrados.append(nombre)

    return DiscoveryResult(
        registered=tuple(registrados),
        failed=fallidos,
        without_tools=tuple(sin_herramientas),
    )
