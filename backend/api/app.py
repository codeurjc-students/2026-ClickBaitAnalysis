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
from typing import Annotated

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.api import history
from backend.api.analyze import analyze
from backend.api.catalog import fetch_catalog
from backend.api.execute import InvalidArguments, ToolNotFound, execute_tool
from backend.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CatalogResponse,
    ExecuteRequest,
    ExecuteResponse,
    HistoryEntry,
    HistoryKind,
    HistoryPage,
    Origin,
)
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

    Cada análisis queda registrado en el historial. Si esa escritura
    falla, la respuesta se devuelve igual: perder un análisis correcto porque el
    disco esté lleno sería peor que no guardarlo.
    """
    respuesta = await analyze(request)

    await history.record(
        kind=HistoryKind.ANALYSIS,
        origin=Origin.API,
        status="ok" if respuesta.has_any_result else "error",
        payload=respuesta.model_dump(mode="json"),
        headline=respuesta.headline,
        verdict=respuesta.verdict.value,
    )
    return respuesta


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


@app.post("/tools/{name}/execute", response_model=ExecuteResponse, tags=["catálogo"])
async def post_execute(name: str, request: ExecuteRequest) -> ExecuteResponse:
    """Ejecuta una herramienta concreta con los argumentos indicados.

    Para cuando no se quieren las cuatro señales —sólo el sentimiento, por
    ejemplo— o para traer una noticia con la que luego analizar.

    Los argumentos se validan contra el `input_schema` que publica `/tools`
    **antes** de invocar, así que un campo mal escrito devuelve un 422 diciendo
    cuál, en vez de llegar como un fallo de ejecución indistinguible de un
    análisis que salió mal.

    Devuelve **404** si la herramienta no existe, **422** si los argumentos no
    encajan, y **200 con `status` en `error`** si la herramienta se ejecutó y
    falló: eso último no es un error HTTP, porque la petición era correcta.
    """
    try:
        respuesta = await execute_tool(name, request.arguments)
    except ToolNotFound:
        raise HTTPException(
            status_code=404, detail=f"No hay ninguna herramienta llamada '{name}'."
        ) from None
    except InvalidArguments as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    # Sólo se registra lo que llegó a ejecutarse. Una petición rechazada por 404
    # o 422 no es una ejecución: ensuciaría el historial con intentos fallidos
    # del formulario en vez de con análisis hechos.
    #
    # Las señales de análisis reciben el titular como argumento, así que se saca
    # de ahí: la entrada se ve en la lista con su titular en vez de con un hueco.
    # Las herramientas que no lo llevan (health_check, get_nyt_news) quedan a None.
    titular = request.arguments.get("headline")
    await history.record(
        kind=HistoryKind.TOOL,
        origin=Origin.API,
        status=respuesta.status.value,
        payload=respuesta.model_dump(mode="json"),
        tool=name,
        headline=titular if isinstance(titular, str) else None,
    )
    return respuesta


@app.get("/history", response_model=HistoryPage, tags=["historial"])
async def get_history(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HistoryPage:
    """Análisis y ejecuciones anteriores, del más reciente al más antiguo.

    Una entrada por **análisis**, no por herramienta invocada: un `/analyze`
    ejecuta cinco señales y produce una sola línea, con su titular y su
    veredicto. La traza de invocaciones vive en los logs, que es donde sirve.

    Cada entrada trae la respuesta completa en `payload`, así que la interfaz
    puede volver a mostrar el resultado sin reejecutar — que además de tardar
    podría dar otro resultado, porque las señales remotas no son deterministas.

    `limit` y `offset` se validan en la firma en vez de recortarse a mano dentro:
    así los topes salen publicados en el esquema OpenAPI —del que se genera el
    cliente Angular— y pedir de más devuelve un **422** diciendo cuál es el
    máximo, en vez de servir otra cosa en silencio.

    El mínimo de 1 no es cosmético: en SQLite un **LIMIT negativo significa «sin
    límite»**, así que `?limit=-1` no daría error, traería la tabla ENTERA a
    memoria y la serializaría. Es el borde que hay que tapar, no el `?limit=9999`.
    """
    filas, total = await history.query(limit, offset)
    return HistoryPage(
        items=[HistoryEntry(**fila) for fila in filas],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/health", tags=["operación"])
async def get_health() -> dict:
    """Estado de las integraciones externas.

    Sondea cada API con una petición ligera y agrega: `ok` si todas responden,
    `degraded` si alguna falla, `down` si ninguna. Es el mismo sondeo que expone
    la tool MCP `health_check`.
    """
    return await check_health()
