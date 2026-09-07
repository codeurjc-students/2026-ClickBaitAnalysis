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
