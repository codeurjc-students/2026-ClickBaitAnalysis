"""Aplicación REST.

**Segundo punto de entrada del backend**, independiente del servidor MCP de
``backend/main.py``: aquel arranca con ``mcp.run(transport="stdio")`` y sirve a
un cliente MCP; éste arranca con uvicorn y sirve al frontend.

    uvicorn backend.api.app:app --reload

Los dos son **fachadas sobre el mismo núcleo**, no una encima de la otra. Por
eso ``/analyze`` llama a la orquestación importándola, y ``/health`` reutiliza
el mismo ``check_health`` que la tool MCP, en vez de dar un rodeo por el
protocolo: pasar por MCP significaría serializar a JSON *string* y volver a
parsear, para acabar en la misma función.

Se descartaron dos alternativas: montar la API dentro de ``main.py`` compartiendo
el objeto ``mcp`` en memoria
y hacer que la API sea cliente MCP por HTTP desde ya (obliga a cambiar el
transporte a ``streamable-http`` antes de necesitarlo). Esa decisión se afronta
al llegar a ``/tools``, que sí necesita la capa MCP: enumerar las herramientas
conectadas en runtime no se puede hacer importando módulos.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.analyze import analyze
from backend.api.catalog import fetch_catalog
from backend.api.schemas import AnalyzeRequest, AnalyzeResponse, CatalogResponse
from backend.config.settings import settings
from backend.core.health import check_health
from backend.core.logging import configure_logging

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configura el logging al arrancar, no al importar.

    Importar el módulo no debe tener efectos secundarios: los tests lo importan
    para construir el cliente y no deberían heredar la configuración global de
    structlog.
    """
    configure_logging()
    log.info(
        "api.start",
        service="clickbait-api",
        nlp_backend=settings.nlp_backend,
        cors_origins=settings.cors_origins,
    )
    yield


app = FastAPI(
    title="ClickBait Analysis API",
    description=(
        "API REST del TFG *Agente inteligente basado en MCP para la detección y "
        "análisis de clickbait en medios digitales*.\n\n"
        "El sistema **no emite un veredicto único de caja negra**: contrasta "
        "varias señales de distinta naturaleza (interpretable, híbrida y opaca) "
        "y las agrupa por lo que miden —forma, engaño y tono—, declarando las "
        "discrepancias en vez de promediarlas."
    ),
    version="0.3.0-dev",
    lifespan=lifespan,
)

# `allow_credentials` concede permiso para que viajen cookies, autenticación
# HTTP y certificados de cliente en peticiones de otro origen (por defecto el
# navegador NO los manda). Queda en False porque aquí no hay ninguna de esas
# cosas: sería conceder un permiso que nadie usa.
#
# Ojo con el malentendido habitual: NO hace falta para tokens `Authorization:
# Bearer`, que son una cabecera corriente cubierta por `allow_headers`. Así que
# probablemente no haya que activarlo ni cuando llegue la autenticación.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.post("/analyze", response_model=AnalyzeResponse, tags=["análisis"])
async def post_analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analiza un titular contrastando todas las señales disponibles.

    Devuelve **200 aunque alguna señal falle**: cada una lleva su propio
    `status`, y perder tres análisis correctos porque el cuarto dio timeout
    sería un error. Si el cuerpo de la noticia no se
    envía, la señal de incoherencia queda en `no_aplicable` y la dimensión de
    engaño no se puede evaluar.
    """
    return await analyze(request)


@app.get("/tools", response_model=CatalogResponse, tags=["catálogo"])
async def get_tools() -> CatalogResponse:
    """Catálogo de herramientas disponibles, descubierto en el momento.

    No es un menú de lanzamiento: responde **qué compone el sistema y con qué
    límites**. Cada herramienta trae su categoría, de qué integración procede y
    —si es una señal de análisis— su ficha de modelo, con el tipo, la dimensión
    que mide y sus límites conocidos.

    Devuelve **200 aunque un servidor MCP no responda**: sale en `servers` con
    estado `unreachable` y `degraded` queda a `true`, pero las herramientas de
    los demás se sirven igual.
    """
    return await fetch_catalog()


@app.get("/health", tags=["operación"])
async def get_health() -> dict:
    """Estado de las integraciones externas.

    Sondea cada API con una petición ligera y agrega: `ok` si todas responden,
    `degraded` si alguna falla, `down` si ninguna. Es el mismo sondeo que expone
    la tool MCP `health_check`.
    """
    return await check_health()
