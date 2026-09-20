"""
Servidor MCP principal.
"""

import structlog
from mcp.server.fastmcp import FastMCP

from backend.analysis import tool as analysis_tool
from backend.config.settings import settings
from backend.core import health
from backend.core.logging import configure_logging
from backend.integrations.discovery import discover_and_register

log = structlog.get_logger()
mcp = FastMCP("tfg-mcp-server")


# Integraciones: se descubren solas recorriendo backend/integrations/.
# Añadir una fuente o una señal es crear su paquete; este fichero no se toca.
integraciones = discover_and_register(mcp)

# Lo que NO es una integración se registra a mano: `discover_and_register` sólo
# recorre `integrations/`, y estas dos no viven ahí ni envuelven nada externo.
#
# - El chequeo de salud es infraestructura básica.
# - El análisis completo es lógica de dominio, y registrarlo desde su propio
#   paquete evita el ciclo que habría si lo hiciera `integrations/nlp/tool.py`:
#   `analysis` ya importa las señales de `nlp`.
#
# Es lo que hace que el agente conversacional pueda reproducir el veredicto del
# formulario en vez de tener que recomponerlo desde las señales sueltas (#107).
health.register(mcp)
analysis_tool.register(mcp)

_HOSTS_LOCALES = ("127.0.0.1", "localhost", "::1")


def configurar_red(servidor: FastMCP, host: str, puerto: int) -> None:
    """Dónde escucha el servidor, y la protección contra DNS rebinding que toca.

    FastMCP decide esa protección AL CONSTRUIRSE, con el host que tenga entonces:
    si es local —y `127.0.0.1` es el defecto—, sólo acepta peticiones con
    `Host: 127.0.0.1` o `localhost`. Cambiar el host después NO la recalcula.
    Medido el 2026-09-17 (#164): con el servidor escuchando en `0.0.0.0` dentro
    de su contenedor, la API lo llamaba como `http://mcp:8765` y recibía `421
    Invalid Host header`.

    Se aplica la misma regla que usa la propia librería al construirse: sólo se
    protege un servidor que escucha en local. Uno en `0.0.0.0` ha declarado que
    se le llama por la red, y la protección es contra un navegador que ataca un
    servidor de su propia máquina — en despliegue el puerto del MCP ni siquiera
    se publica.

    Es una función y no un argumento del constructor porque el servidor se crea
    al importar, y leer la configuración al importar es lo que #87 quitó: así
    `main()` la lee al arrancar, y se puede probar sobre un servidor nuevo.
    """
    servidor.settings.host = host
    servidor.settings.port = puerto
    if host not in _HOSTS_LOCALES:
        servidor.settings.transport_security = None


def main():
    # Initialize and run the server
    configure_logging()

    # host/port los ignora el transporte stdio.
    configurar_red(mcp, settings.mcp_host, settings.mcp_port)

    log.info(
        "server.start",
        server="tfg-mcp-server",
        transport=settings.mcp_transport,
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=settings.log_level,
        log_format=settings.log_format,
        # Qué se descubrió. Si una integración falló al cargar, sus tools no
        # existen y el sistema queda degradado en silencio: aquí es donde se ve.
        integraciones=list(integraciones.registered),
        integraciones_fallidas=integraciones.failed or None,
    )
    mcp.run(transport=settings.mcp_transport)


if __name__ == "__main__":
    main()
