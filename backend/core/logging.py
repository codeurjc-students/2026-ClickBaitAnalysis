"""La configuración de structlog, común a la API y al servidor MCP.

`configure_logging` la llaman el arranque de la API (su `lifespan`) y el de
`main.py`, nunca el import: así los tests no heredan la configuración global.
Escribe por **stderr** porque el transporte stdio de MCP usa stdout, y baja
`httpx` a WARNING porque sus trazas de nivel INFO llevan la URL entera, con la
clave de Guardian y de NYT dentro.

`avisar_si_faltan_claves` la llaman los dos arranques justo después (#259).
"""

import logging
import sys

import structlog

from backend.config.settings import settings


def configure_logging():
    level_int = logging.getLevelNamesMapping()[settings.log_level]
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    logging.getLogger("httpx").setLevel(
        logging.WARNING
    )  # Evita Filtraciones de API KEY por logs.
    # El `else` que lanza no es defensa contra lo imposible: `log_format` es un
    # `Literal` de dos valores, así que hoy no puede caer ahí. Existe para el día
    # que se añada un tercero — sin él, `renderer` quedaría SIN ASIGNAR y la
    # línea siguiente reventaría con un `UnboundLocalError` que no dice nada del
    # problema real. Detectado por pyright en #139.
    if settings.log_format == "console":
        renderer = structlog.dev.ConsoleRenderer()
    elif settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        raise ValueError(f"Formato de log no soportado: {settings.log_format}")

    processors.append(renderer)
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level_int),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        # imprimir por stderr ya que MCP imprime por stout tambien.
    )


def avisar_si_faltan_claves() -> None:
    """Un aviso en el registro con las claves de API sin configurar, si falta alguna.

    Desde #259 ninguna es obligatoria: sin ellas el proceso arranca, que es lo
    que se quería, y cada herramienta dice qué le falta. Pero quien despliega
    tiene que verlo nada más arrancar, que es lo que antes hacía visible el
    fallo. Lleva los NOMBRES de las variables, nunca los valores.
    """
    if claves := settings.claves_sin_configurar():
        structlog.get_logger().warning(
            "configuracion.claves_sin_configurar", claves=claves
        )
