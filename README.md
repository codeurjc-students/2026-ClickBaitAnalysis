# 2026-ClickBaitAnalysis

Version de Python: 3.12.3

---

## Convenciones de desarrollo

### Ramas

Cada rama parte de `main` y sigue el patrón `<tipo>/<descripción-corta>`:

| Prefijo | Uso |
|---|---|
| `feature/` | Nueva funcionalidad |
| `fix/` | Corrección de bug |
| `chore/` | Setup, estructura, mantenimiento |
| `docs/` | Documentación |
| `test/` | Tests nuevos o mejoras de cobertura |

### Commits — Conventional Commits

Formato: `tipo(scope): descripción`

**Tipos:** `feat`, `fix`, `chore`, `docs`, `test`, `refactor`

**Scopes:** `core`, `integrations`, `settings`, `tests`, `docs`

Ejemplos:
```
feat(integrations): añadir tool get_news_this_week para Guardian API
chore(settings): configurar pydantic-settings con validación al inicio
fix(core): corregir serialización de ToolResult en tools MCP
test(integrations): añadir tests unitarios para weather tools
```

### Merge a main

- Se usa **squash merge** vía Pull Request.
- Cada PR debe estar vinculado a una issue con `Closes #N`.

---

## Recopilación de épicas

Aquí se documentan las épicas y las iteraciones realizadas durante el desarrollo del proyecto. No se trata de un documento final sino simplemente un histórico de progreso para la memoria final.

## Épica 0 — Experimentación con MCP y APIs externas (MARZO - MEDIADOS DE ABRIL)

Objetivo: validar la viabilidad de construir un servidor MCP en Python que exponga herramientas (tools) capaces de consultar APIs externas reales, estableciendo las bases de arquitectura sobre las que se apoyará el resto del proyecto.

### Iteraciones

#### 0.1 — Prototipo MCP con Weather.gov
- Creación de `weather.py` como script monolítico de prueba.
- Integración con la API pública de [NOAA Weather.gov](https://api.weather.gov) para obtener alertas meteorológicas por estado y previsiones a partir de coordenadas.
- Añadidos `requirements.in` y `requirements.txt` con las dependencias base: `mcp`, `fastmcp`, `httpx`.

#### 0.2 — Estructura de paquete `backend/`
- Extracción del prototipo a una arquitectura en capas: `backend/api/`, `backend/tools/`, `backend/main.py`.
- `main.py` instancia el servidor FastMCP y registra las tools disponibles.
- Separación de responsabilidades: la capa API gestiona las llamadas HTTP; la capa de tools expone las funciones al servidor MCP.

#### 0.3 — Modelo de respuesta estandarizado (`ToolResult`)
- Introducción de `ToolResult` (Pydantic `BaseModel`) en `backend/models.py` para unificar el contrato de respuesta entre la capa API y las tools.
- Campos: `success: bool`, `data: Any | None`, `error: str | None`.
- Métodos de fábrica: `ToolResult.ok(data)`, `ToolResult.fail(error_message)` y predicado `has_content()`.

#### 0.4 — Integración con The Guardian API
- Añadida `GuardianAPI` en `backend/api/the_guardian_api.py` para consultar artículos de la última semana por tema (`get_news_this_week_call`).
- Registrada la tool `get_news_this_week` en el servidor MCP.
- Primer test exploratorio en `tests/simple_test.py`.

#### 0.5 — Refactor: herencia desde `BaseAPI`
- Creada la clase abstracta `BaseAPI` en `backend/api/base_api.py` con el método genérico `make_request(endpoint, method, params)`.
- `WeatherAPI` y `GuardianAPI` heredan de `BaseAPI`, eliminando duplicación de lógica HTTP (timeout, errores HTTP, manejo de excepciones).
- `make_request` inyecta automáticamente la API key si está configurada.

#### 0.6 — Corrección de tipos y uso correcto de la capa API (PR #1)
- Las tools instancian y usan correctamente los objetos API en lugar de llamar funciones sueltas.
- Los tipos de retorno de las tools se limitan a tipos serializables (`str | dict`) compatibles con el protocolo MCP.

### Decisiones de diseño relevantes

| Decisión | Motivo |
|---|---|
| FastMCP como framework MCP | Reduce el boilerplate del protocolo y permite registrar tools con un simple decorador `@mcp.tool()` |
| `httpx.AsyncClient` para HTTP | API totalmente asíncrona, coherente con el modelo async/await del servidor |
| `ToolResult` como capa de abstracción | Desacopla el manejo de errores HTTP del código de las tools; facilita los tests unitarios |
| Herencia `BaseAPI` | Centraliza timeout, inyección de API key y manejo de excepciones HTTP en un único lugar |

---

## Épica 1 — Infraestructura MCP ()

### Iteraciones

#### 1.1 — Incidente: filtración de API key y rotación

Debido a un descuido y una experimentación algo apresurada, la clave API fue filtrada en github y tuve que cambiarla. Este error fue un toque de conciencia para empezar a definir una estructura completa del proyecto en épicas y priorizar las más relevantes. 

#### 1.2 — E1-01 + E1-03 · Migración de estructura a `core/` + `integrations/<nombre>/`

Antes de crear nuevos archivos y carpetas, decidí definir la estructura del proyecto primero, pero con un enfasis en YAGNI, la estrucutra podría ser modificada SOLO cuando sea necesario, sin intentar predecir como será a futuro:

Por el momento dentro de backend tenemos:
- Core: Con una clase API para hacer peticiones básicas y un archivo de modelos personalizados para las tools.

- Integration: que contiene varias subcarpetas, cada una relacionada con un API y que a su vez contiene las peticiones (client) y las tools que expone al MCP (tool)

- Test: Carpeta que contendrá tests en el futuro, por ahora un placeholder

Ya que en la próxima épica se tratarán las variables de configuracion, se creó la carpeta config.






#### 1.3 — E1-04 · Gestión de configuración con `pydantic-settings`

Para evitar nuevas filtraciones accidentales de la API key en el código, doy prioridad a establecer las variables de configuración del proyecto. Decidí usar pydantic-settings y no os.getenv por el fail fast y escalabilidad de variables a futuro.


La clase settings.py maneja ahora todas las variables de configuración y seguridad, conectandose con el archivo .env (el cual nunca está en el git ignore)

Siguiente paso: Manejo de tests para depurar llamadas a API, pues algo falla.


### 1.4 - E1-02 · Formalizar convención de ramas y commits

Aunque se trate de un paso pequeño, antes de seguir trabajando en las épicas pensé que sería necesario formalizar la creación de ramas y commits para mejorar la organización del proyecto a largo plazo

Se usará Conventional Commits por simplicidad, empezando cada rama por el tipo de épica al que hace referencia (chore, fix, fet, docs) y con commits usando "scopes" que vienen a indicar sobre que parte del proyecto se trabajó. Esto es también útil para no subir macro-commits que afecten a demasiados archivos y poder hacer "rollback" de ser necesario.

Ejemplos: 

feat(integrations): añadir tool get_news_this_week para Guardian API
chore(settings): configurar pydantic-settings con validación al inicio

#### 1.5 — E1-09 · Configurar pytest y estructura de tests

Se instalaron pytest, pytest-asyncio y pytest-cov como dependencias de desarrollo. Se creó `pytest.ini` en la raíz del proyecto con configuración mínima (testpaths y pythonpath). Se añadió un smoke test (`tests/test_smoke.py`) que verifica que el servidor MCP importa sin errores.

#### 1.6 — E1-10 · Tests unitarios para weather tools

Se añadió `respx` para mockear llamadas HTTP en tests. Tests implementados para `get_alerts_API` (respuesta válida, vacía y error HTTP) y para `get_forecast` (respuesta válida con mockeo de dos llamadas encadenadas, error HTTP en `get_zone_by_points` y error HTTP en `get_forecast_API`). Durante el testing se descubrió y corrigió un bug en `get_zone_by_points` donde faltaba `/` en la URL construida. Se añadió también validación de periods vacíos en `tool.py`; el test correspondiente queda fuera del scope de esta iteración por depender de la capa tool y no del client.

#### 1.7 — E1-06 · Logging estructurado con `structlog`

El criterio de aceptación del issue (`logger.info("test", key="value")` debe producir salida estructurada) descartó el `logging` estándar de Python, que no acepta kwargs arbitrarios — se eligió `structlog` por soportar esa sintaxis de forma nativa. (Básicamente, el logging básico fija las salidas a ciertos argumentos. Utilizar structlog nos permite más libertad al configurarlos)

La configuración vive en `backend/core/logging.py` (función `configure_logging()`) y se controla desde dos nuevas variables en `Settings` (`backend/config/settings.py`):

- `LOG_LEVEL`: `DEBUG` / `INFO` / `WARNING` / `ERROR` (default `INFO`).
- `LOG_FORMAT`: `console` (renderer legible y coloreado, default para desarrollo) o `json` (renderer estructurado para producción).

Ambas se declaran como `Literal[...]` en pydantic-settings, de modo que un valor inválido falla al arrancar (fail-fast, coherente con la decisión de E1-04). La pipeline de processors aplica `merge_contextvars`, `add_log_level` y un `TimeStamper` ISO en UTC antes del renderer final.

En `backend/main.py` se invoca `configure_logging()` al inicio de `main()` y se reemplaza el `logging.info("Starting server...")` por `log.info("server.start", transport="stdio")`, ya con campos estructurados. El test `tests/test_logging.py` valida el DoD del issue forzando `LOG_FORMAT=json` con `monkeypatch` y verificando que la salida JSON contiene `event`, `key`, `level` y `timestamp`.

#### 1.8 — E1-07 · Registro de invocaciones de tools

Se añade `backend/core/observability.py` con el decorador `log_tool_invocation`, que envuelve cada tool MCP para registrar cada invocación con `tool` (nombre), `params` (kwargs recibidos, ya que MCP transmite los parámetros como JSON object), `duration_ms` medido con `time.perf_counter()` y un booleano `success`.

El decorador se aplica en cascada con `@mcp.tool()`:

```python
@mcp.tool()
@log_tool_invocation
async def get_alerts(state: str) -> str | dict: ...
```

El orden importa — Python aplica los decoradores de abajo a arriba, así que `@mcp.tool()` registra ya la versión envuelta con logging. Aplicado a las tres tools existentes (`get_alerts`, `get_forecast`, `get_news_this_week`).

En caso de éxito se emite el evento `tool.invoke`. Si la tool lanza una excepción, se emite `tool.invoke.failed` con el traceback completo (`traceback.format_exc()` en el campo `exception`) y la tool devuelve al cliente MCP un mensaje genérico (`"Internal error while executing tool"`) — el detalle interno solo aparece en el log.

**Limitación conocida:** cuando una tool retorna un string de error sin lanzar excepción (patrón actual de `get_alerts` y `get_news_this_week`: `return response.error or "Error fetching..."`), el decorador no puede distinguir éxito real de error suave y lo loguea como `success=True`. Estabilizar ese contrato queda fuera del scope de E1-07 y será cubierto por los issues #13 (`[E1-11]`) y #14 (`[E1-12]`).

El test `tests/test_observability.py` cubre dos casos con `pytest-asyncio`: invocación correcta (assert sobre `event`, `tool`, `params`, `success=True`, `duration_ms`) y excepción (assert sobre `event=tool.invoke.failed`, `success=False`, presencia del traceback en `exception`, valor devuelto = mensaje genérico).

#### 1.9 — E1-12 · Fix: `get_news_this_week` con respuestas sin `results`

`backend/integrations/news/client.py:get_news_this_week_call` rompía con `TypeError: 'NoneType' object is not iterable` cuando la respuesta de The Guardian no incluía la clave `results` (o llegaba como `null`). El list comprehension iteraba directamente sobre `response.data.get("response", {}).get("results")` sin validar.

Con el decorador `log_tool_invocation` (E1-07) la excepción se capturaba ahora como `tool.invoke.failed` y el cliente MCP recibía `"Internal error while executing tool"` — funcional, pero "no hay artículos" no debería ser un error técnico, sino un resultado legible.

**Fix:** un guard antes del list comprehension:

```python
results = response.data.get("response", {}).get("results")

if not results:
    return ToolResult.fail("No articles found")
```

`not results` cubre con una sola línea tanto `None` (clave ausente o `null` explícito) como `[]` (lista vacía).

**Contrato:** se eligió `ToolResult.fail("No articles found")` sobre la alternativa `ToolResult.ok("...")` por dos razones:

1. **Tipo único de `data`:** en éxito, `data` siempre es `list[dict]`; un string vacío como `data` rompería esa consistencia.
2. **Output limpio al cliente:** la tool serializa `response.data` con `json.dumps(...)` solo cuando `has_content()`; si `data` fuera un string, saldrían comillas dobles literales (`'"No articles found."'`). Por el camino `fail`, la tool devuelve `response.error` directamente — string limpio.

El test `tests/test_news_guardian.py` cubre tres casos con `respx`: respuesta válida con artículos (verifica `success=True` y campos `title`/`url`/`date`), `results=[]` (verifica el guard sobre lista vacía) y respuesta sin la clave `results` (verifica el guard sobre `None`, que era el escenario del bug original).

#### 1.10 — E1-08 · Health check con probes activos

Se añade `backend/core/health.py` con la tool MCP `health_check`, que reporta el estado del servidor y de sus dependencias externas haciendo una petición real a cada API. Devuelve un dict con:

- `status`: `Literal["ok", "degraded", "down"]` — agregado por la función pura `_aggregate_status` según cuántas integraciones respondan.
- `timestamp`: ISO 8601 en UTC (`datetime.now(timezone.utc).isoformat()`).
- `integrations`: dict por integración (`weather`, `guardian`) con `reachable: bool` y `error: str | None`.

Los probes se ejecutan **en paralelo con `asyncio.gather`**, así la latencia total es `max(probes)` y no `sum(probes)` — relevante con timeout corto (5s) y dos integraciones. Cada probe usa `httpx.AsyncClient` directo (sin pasar por `BaseAPI`) porque la lógica es trivial y la inyección automática de API key no aporta para una petición one-shot. Para Guardian la key se pasa explícita en `params={"api-key": settings.guardian_api_key}`; `raise_for_status()` convierte 4xx/5xx en excepción para que el `except httpx.HTTPError` los trate uniformemente como `reachable=False`.

**Sub-fix incluido:** `backend/core/logging.py` redirige structlog a `sys.stderr` mediante `logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)`. El protocolo MCP por stdio reserva **stdout para JSON-RPC** y **stderr para logs del servidor**; sin este fix, structlog escribía sobre stdout y mezclaba con el protocolo, lo que hacía que Claude Desktop no pudiera parsear las respuestas y el servidor pareciese "muerto" desde el cliente. Deuda heredada de E1-06 que se descubrió al integrar en Claude Desktop por primera vez.

Los tests viven en `tests/test_health.py` y combinan **dos niveles** deliberadamente:

- **Unit tests (3)** sobre `_aggregate_status` — función pura, sin red ni mocks. Cubren los tres estados con dicts dummy. Mantienen valor real porque la lógica de agregación tiene 3 ramas no triviales.
- **Integration tests (2)** marcados con `@pytest.mark.integration` que invocan `_probe_weather` y `_probe_guardian` contra las APIs reales. Verifican comportamiento end-to-end: conectividad de red + validez de la API key + contrato HTTP.

Se descartó la opción de mockear las APIs con `respx` (patrón que sí se usa en `test_weather.py` y `test_news_guardian.py`): un mock de la integración que el health debe detectar no aporta en un proyecto de un solo programador frente a un test real automatizado que sirve también como pre-deploy check. El marker `integration` está declarado en `pytest.ini` para separar ejecuciones (`pytest -m "not integration"` cuando no haya red o API key).

### Decisiones de diseño relevantes

| Decisión | Motivo |
|---|---|
| Uso de pydantic-settings | Evitar filtraciones de variables críticas y valores hardcodeados |
| `structlog` sobre `logging` stdlib | Soporta kwargs estructurados (`log.info("evt", key=value)`) sin recurrir a `extra={...}`; pipeline de processors configurable con renderer condicional console/json |
| Decorador `log_tool_invocation` sobre middleware | FastMCP no expone un punto claro de middleware; un decorador propio es portable, fácil de testear de forma aislada y se compone explícitamente con `@mcp.tool()` |
| Mensaje genérico al cliente en error | Evita filtrar detalles internos (paths, librerías, stack) en la respuesta MCP; el detalle solo vive en el log interno (Req 1.5) |
| `asyncio.gather` para probes en paralelo | Latencia total = `max(probes)` en lugar de `sum`; con dos integraciones y timeout 5s, evita esperas innecesarias |
| Logs por `sys.stderr` en transporte stdio | El protocolo MCP por stdio reserva stdout para JSON-RPC; sin redirigir, structlog corrompe el canal y Claude Desktop pierde el servidor |
| Integration tests sobre mocks para health | Para un solo programador, automatizar la detección real de fallos vale más que mocks que reproducen exactamente la funcionalidad bajo test |

---

## Épica 2 — Integración New York Times

Objetivo: añadir una segunda fuente de noticias al servidor MCP para alimentar el análisis de clickbait con titulares de procedencia distinta a The Guardian. La épica se descompone en cliente (E2-01), tool MCP (E2-02) y tests (E2-03), siguiendo el mismo patrón de integraciones ya consolidado.

### Iteraciones

#### 2.1 — E2-01 · Cliente NYT con búsqueda de titulares

Se añade `backend/integrations/nyt/` con `NYTAPI` heredando de `BaseAPI`, replicando el patrón de `GuardianAPI`: constantes de clase (`BASE_URL`, `API_KEY`, `API_KEY_PARAM`) y `make_request` ya inyecta la `api-key` como query string sin tocar el método.

`Settings` extendido con `nyt_api_key: str` (obligatoria, fail-fast vía pydantic-settings). En `.env` se carga como `NYT_API_KEY` (mayúsculas, convención 12-factor; pydantic-settings mapea automáticamente).

El único método público es `search_articles(topic: str)`, que llama a [Article Search API](https://developer.nytimes.com/docs/articlesearch-product/1/overview) con `q=<topic>`, `begin_date=YYYYMMDD` (hoy menos 7 días) y `sort=newest`. Devuelve `ToolResult.ok(list[dict])` con el mismo schema común que Guardian — `{title, url, date}` — para que el consumidor (la tool MCP de E2-02) no tenga que distinguir el origen.

#### 2.2 — E2-02 · Tool MCP `get_nyt_news`

Se añade `backend/integrations/nyt/tool.py` con la función `register(mcp)`, siguiendo el mismo patrón de `news/tool.py`, y maneja el `ToolResult` con el mismo contrato que Guardian — `if not response.has_content(): return response.error or "Error fetching news"` y `json.dumps(response.data)` en éxito.

`backend/main.py` registra la nueva tool junto a las anteriores (`nyt_tool.register(mcp)`), elevando a **5 las tools expuestas** al cliente MCP: `get_alerts`, `get_forecast`, `get_news_this_week`, `health_check` y `get_nyt_news`.

#### 2.3 — E2-03 · Tests del cliente NYT

`tests/test_news_nyt.py` combina **dos niveles** siguiendo el patrón establecido en E1-08 (health check):

**Unit tests (4 con `respx`)**, deterministas, cubren todas las ramas de parseo:

- `test_search_articles_valid_response` — payload OK con artículos, asserta `success=True` y mapeo de campos `headline.main`/`web_url`/`pub_date` al schema común `{title, url, date}`.
- `test_search_articles_no_results` — `docs=[]`, asserta `success=False` con `"No articles found"` en `error`. Cubre el guard `if not docs`.
- `test_search_articles_missing_docs_key` — payload sin la clave `docs`, cubre el mismo guard sobre `None`.
- `test_search_articles_http_error` — respuesta HTTP 500, asserta que `BaseAPI` propaga el fallo y `search_articles` retorna `ToolResult.fail`.

**Integration tests (2 con `@pytest.mark.integration`)**, hacen petición real a NYT:

- `test_search_articles_valid_use` — drift detection del schema: con la API key real, asserta que cada artículo de la respuesta contiene `title`, `url` y `date`. Si NYT renombra o anida distinto algún campo, el test falla y se entera el dev.
- `test_search_articles_invalid_topic` — topic improbable (`"nonexistingtopicabcde"`) que actualmente no devuelve resultados; asserta `not result.success` y `"No articles found" in result.error`, conectando el contrato del cliente con el string que finalmente recibe el LLM. **Aceptado como potencialmente flaky** (algún día puede aparecer un artículo con ese topic); documentado en el propio archivo como warning.

#### 2.4 — E1-13 · Tests de integración para Guardian (cierre de asimetría)

Como follow-up de E2-03 se replicó el patrón mixto unit + integration en `tests/test_news_guardian.py`, que hasta entonces solo tenía cobertura con mocks. Cierra la asimetría: ahora las dos integraciones de noticias (Guardian y NYT) tienen el mismo nivel de cobertura, incluyendo drift detection del contrato real con la API.

### Decisiones de diseño relevantes

| Decisión | Motivo |
|---|---|
| Schema común `{title, url, date}` entre Guardian y NYT | Permite que la futura tool MCP (E2-02) y el analizador NLP (E3) consuman datos sin ramificar lógica por fuente |
| Hereda de `BaseAPI` igual que Guardian/Weather | Reutiliza la inyección automática de `api-key`, manejo uniforme de timeout y errores HTTP; cualquier mejora futura en `BaseAPI` aplica a las tres integraciones |

---

## Refactor transversal de coherencia (post-MVP)

Tras cerrar E2, un repaso del proyecto destapó deuda e inconsistencias acumuladas entre épicas. Se abordaron en un PR de refactor (sin nueva funcionalidad de producto), agrupadas por tema.

### Health check dinámico (+ NYT)

`backend/core/health.py` tenía una función `_probe_*` por integración (`_probe_weather`, `_probe_guardian`) con estructura `try/except/raise_for_status` **idéntica** — repetición real. Se extrajo un único `_probe(url, params)` genérico y las integraciones se declaran como **datos** en un diccionario `PROBES`. Beneficio doble: añadir una API = una entrada (no más funciones), y **NYT entró de paso** (el health check ignoraba NYT pese a ser la tercera integración — incoherencia heredada de cuando se diseñó E1-08, antes de que NYT existiera). Los integration tests pasaron a `@pytest.mark.parametrize` sobre `PROBES`, generándose uno por integración automáticamente.

Se distinguió esta repetición **real** de la **aparente** del registro de tools en `main.py`: ahí cada `*.register(mcp)` invoca módulos distintos sin patrón que extraer, así que el "register dinámico" se descartó (YAGNI) — explícito es más legible que un loop o autodescubrimiento mágico con `importlib`.

### `topic` opcional + `days` configurable en clientes y tools

Los clientes de noticias tenían `topic` obligatorio y rango temporal fijo (7 días hardcodeado). Se hizo `topic: str | None = None` (si se omite, devuelve lo más reciente sin filtrar) y `days: int = 7` configurable. Los params se construyen condicionalmente: la clave `q` solo se envía si hay `topic`.

Decisión clave de **frontera de confianza**: al exponer `days` también en las tools (para que el usuario final pueda pedir rangos vía el LLM), `days` pasó de input interno a input **no confiable** del LLM. Por eso se validó **en la tool** con `pydantic.Field(ge=1, le=30)` — el rango aparece en el schema que ve el LLM y FastMCP rechaza valores fuera de rango antes de ejecutar. El cliente no revalida: la frontera ya filtró.

### Rename por coherencia

`get_news_this_week_call` (cliente Guardian) pasó a `search_articles`, idéntico a NYT — ambos clientes exponen ahora la misma interfaz, reforzando el schema común. La tool `get_news_this_week` pasó a `get_guardian_news`, simétrica con `get_nyt_news` y nombrando la fuente para que el LLM desambigüe mejor. El nombre viejo (`this_week`) además se había vuelto engañoso al hacer `days` configurable.

### Limpieza

- Eliminado `tests/simple_test.py` (código muerto de E0: importaba de `backend.api.the_guardian_api`, ruta que desapareció en la migración E1-03; pytest no lo recogía por no matchear `test_*.py`).
- `tests/test_logging.py` y `tests/test_observability.py` leían `capsys` desde **stdout**, pero desde el fix de stderr de E1-08 los logs salen por **stderr**. Tests desincronizados (latentes hasta correrlos juntos): se corrigieron a `captured.err`. Ahora además verifican que los logs van a stderr, justo lo que el protocolo MCP stdio exige.
- Start del servidor más descriptivo: el log `server.start` incluye ahora `log_level` y `log_format` (QoL para diagnóstico al arrancar).
- Imports muertos (`Optional`, `ToolResult` sin usar), `f""` sin interpolación y TODOs vagos eliminados.

### Decisiones de diseño relevantes

| Decisión | Motivo |
|---|---|
| `_probe` genérico + dict `PROBES` (health) | Repetición real entre probes; añadir integración = una entrada de datos. Distinto del register de `main.py`, donde la repetición es aparente y explícito gana |
| Validar `days` con `Field` en la tool, no en el cliente | La frontera de confianza está en la tool (input del LLM); validar una vez en el borde, el cliente confía en lo que recibe |
| `topic` opcional construyendo params condicionalmente | Evita enviar `q=None` a la API; permite el caso "titulares recientes sin tema" |
| Rename a `search_articles` / `get_guardian_news` | Interfaz idéntica entre clientes y tools simétricas que nombran la fuente; el nombre viejo era engañoso con `days` configurable |

---

## Integración continua

### E1-14 · CI con GitHub Actions

Se añadió `.github/workflows/ci.yml`, un workflow que ejecuta la suite de tests en cada `pull_request` hacia `main` (y en `push` a `main`). El job configura Python 3.12, instala `requirements.txt` y corre `pytest -m "not integration"`. Es la red de seguridad que da sentido al esfuerzo de testing acumulado: un cambio que rompa el código se detecta en el PR, antes del merge.

### E1-15 · Renombrar paquete `news/` → `guardian/`

El paquete `backend/integrations/news/` contenía en realidad la integración de The Guardian, mientras NYT vivía en `backend/integrations/nyt/`: asimetría `news`=Guardian vs `nyt`=NYT. Se renombró a `backend/integrations/guardian/` para que el nombre del paquete refleje la fuente, igual que NYT. Cambios asociados: imports en `main.py` (incluido el alias `news_tool` → `guardian_tool`), el import interno de `guardian/tool.py`, y el test `tests/test_news_guardian.py` renombrado a `tests/test_guardian.py`. El movimiento se hizo preservando el historial git de los archivos.

Fue el **primer PR validado por el CI de E1-14** antes del merge — estreno de la red de seguridad sobre un cambio mecánico pero con riesgo real de romper imports.

## Épica 3 — NLP via HuggingFace

> **Estado:** E3-01 (cliente `HFClient`) ✅ mergeado (PR #40). E3-02 (detección de clickbait, zero-shot) en curso. E3-03 (sentimiento) y E3-04 (tests) pendientes.

### Conceptos NLP (sin asumir experiencia previa)

**1. Clasificar texto = ponerle una etiqueta.** Un clasificador recibe un texto (un titular) y le asigna una etiqueta de un conjunto, con un *score* de confianza (0–1). Ej.: clickbait → `{clickbait, no-clickbait}`.

**2. Modelo *fine-tuned* específico** (lo que son `elozano` o `distilbert-sst2`). Se entrena con miles de ejemplos **ya etiquetados** de **una** tarea. La aprende muy bien, pero: sus etiquetas son **fijas**, necesitas un modelo por tarea, y —clave aquí— alguien tiene que tenerlo **desplegado** para usarlo por API. Los de clickbait no lo están en el serverless de HF.

**3. *Zero-shot classification* = clasificar SIN haber entrenado para esas etiquetas.** Le pasas el texto **y** las etiquetas candidatas *en el momento de la consulta* (`["clickbait", "factual"]`) y el modelo puntúa cuánto encaja cada una. No fue entrenado para "clickbait"; razona sobre la marcha. Por eso puedes **cambiar las etiquetas sin reentrenar nada**.

**4. ¿Cómo hace esa "magia"? Con NLI (*Natural Language Inference*).** NLI es una tarea clásica: dadas dos frases —una **premisa** y una **hipótesis**— decidir si la premisa **implica** (*entailment*), **contradice** o es **neutral** respecto a la hipótesis. Ej.: premisa *"El gato duerme en el sofá"* → hipótesis *"Hay un animal en el sofá"* = *entailment*.

El truco del zero-shot es **reformular la clasificación como NLI**:
- **Premisa** = el titular.
- **Hipótesis** = una plantilla por etiqueta: *"Este texto es clickbait"*, *"Este texto es una noticia factual"*.
- La probabilidad de *entailment* de cada hipótesis se usa como **score** de esa etiqueta; la de mayor *entailment* gana.

Por eso los modelos zero-shot son en realidad modelos **entrenados en NLI**, como `facebook/bart-large-mnli` (entrenado en el dataset MNLI).

**5. *Cross-encoder* vs *bi-encoder*.** Es **cómo** el modelo compara las dos frases:
- **Cross-encoder:** mete premisa + hipótesis **juntas** en la misma pasada; las "lee" a la vez y da un score de relación. Muy **preciso**, pero **lento**: hay que reprocesar por cada par → con N etiquetas, N pasadas. Los `cross-encoder/nli-deberta-...` son esto.
- **Bi-encoder:** codifica cada frase **por separado** en un vector y compara vectores. **Rápido** y reutilizable, pero menos preciso en juicios par-a-par.

Para clasificar pocos titulares con pocas etiquetas, el coste de las N pasadas del cross-encoder es asumible y **ganas precisión**.

**6. Ejemplo real** (zero-shot con `facebook/bart-large-mnli`, etiquetas `["clickbait", "factual news"]`):

| Titular | `clickbait` | `factual news` |
| :--- | :---: | :---: |
| *"You will not believe what happened next"* | **0.79** | 0.21 |
| *"Federal Reserve raises interest rates by a quarter point"* | 0.17 | **0.83** |

Sin entrenar nada específico de clickbait, el modelo discrimina correctamente.

> **Estado de diseño:** decisiones tomadas antes de codificar. La elección final de modelo de cada tarea se documenta en su iteración (E3-02 clickbait, E3-03 sentimiento).

### Evaluación de modelos candidatos

Para el análisis de los titulares en el servidor MCP se han evaluado las siguientes opciones de modelos ligeros de Hugging Face, priorizando un balance entre baja latencia y precisión. Son **candidatos**: el modelo definitivo de cada tarea se fija en su issue (E3-02 clickbait, E3-03 sentimiento).

| Categoría | Modelo (Hugging Face) | Ventajas (Pros) | Desventajas (Contras) |
| :--- | :--- | :--- | :--- |
| **Sentimiento (Inglés)** | `cardiffnlp/twitter-roberta-base-sentiment-latest` | • Excelente precisión con texto corto.<br>• Entiende matices periodísticos y sarcasmo.<br>• Clasificación en 3 vías (Positivo, Negativo, Neutral). | • Ligeramente más pesado en RAM/VRAM.<br>• Inferencia marginalmente más lenta que modelos destilados. |
| **Sentimiento (Inglés)** | `distilbert/distilbert-base-uncased-finetuned-sst-2-english` | • Inferencia ultra-rápida (ideal para latencia crítica).<br>• Consumo mínimo de recursos (modelo *distilled*). | • Solo clasificación binaria (Positivo/Negativo, omite neutralidad).<br>• Menor capacidad para captar ironías complejas. |
| **Clickbait (Específico)** | `elozano/bert-base-cased-clickbait-news` | • Solución "Plug & Play" (enchufar y listo).<br>• Entrenado específicamente con titulares de noticias. | • Difícil de ajustar (no puedes redefinir qué es "clickbait").<br>• Puede fallar con el clickbait sutil o "elegante" (ej. NYT). |
| **Clickbait (Zero-Shot)** | `cross-encoder/nli-deberta-v3-small` | • Control total: permite definir tus propias etiquetas (ej. `["factual", "sensationalism"]`).<br>• Excelente capacidad de razonamiento lógico e inferencia. | • Requiere afinar empíricamente las etiquetas de entrada.<br>• Inferencia ligeramente más computacional al evaluar múltiples etiquetas. |
| **Traducción (EN ➔ ES)** | `Helsinki-NLP/opus-mt-en-es` | • Ejecución 100% local y privada (sin costes de API externa).<br>• Extremadamente ligero (~300MB).<br>• Traducciones rápidas de oraciones cortas. | • Calidad ligeramente inferior a APIs comerciales (DeepL/OpenAI) en textos muy literarios.<br>• Añade un paso extra de procesamiento al pipeline del MCP. |

#### Backend de inferencia: remoto ahora, local pendiente

Para el MVP se ejecutan en **remoto**; el salto a **local** queda supeditado a si hay infraestructura de cómputo disponible (p. ej. de la universidad). Comparativa:

- **Remoto — HF Inference API:** disponible ya, sin GPU propia. HF asume el cómputo; a cambio se paga en latencia de red, *rate limits* y dependencia de un token (`HF_TOKEN`). Encaja con `BaseAPI` (HTTP) extendiéndola a `POST` + header `Authorization: Bearer`.
- **Local — `transformers`:** descarga los pesos y usa RAM/VRAM propias, pero da privacidad total y sin *rate limits*. No usa `BaseAPI`.

**Decisión para no bloquear la épica:** el cliente NLP se programa contra una **interfaz estable** (`classify` / `zero_shot` → `{label, score}`); las tools (`detect_clickbait`, `analyze_sentiment`) y sus tests dependen del *contrato*, no de la implementación: pasar de remoto a local más adelante es escribir otra implementación detrás de la misma interfaz, sin tocar las tools. Se empieza por **remoto**, que no depende de infraestructura externa. Un futuro selector `nlp_backend` (remoto/local) se añadirá **junto con** el backend local (hoy no lo leería nadie → aplazado, *YAGNI*).

> **Sobre la tabla:** las ventajas/inconvenientes de **RAM/VRAM, "100% local" y tamaño en disco** solo aplican al backend local; en remoto ese coste lo absorbe HF. Los modelos son los mismos en ambos casos.

> **Alcance:** la **traducción EN→ES** (`Helsinki-NLP/opus-mt-en-es`) es una capacidad candidata adicional, aún no comprometida en el MVP (las 2 tools núcleo son clickbait y sentimiento).

### E3-01 · Cliente HuggingFace (`HFClient`) — realizado

Primer cliente que rompe el patrón GET + api-key en query: HF exige **POST con body JSON** y **auth por header** `Authorization: Bearer`. Cambios:

- **`Settings`:** nueva variable obligatoria `hf_token` (`HF_TOKEN` en `.env`), fail-fast.
- **`BaseAPI`:** soporte de `POST` con body JSON, y auth delegada en un método sobreescribible `_apply_auth` (por defecto, api-key en query → Guardian/NYT intactos). La subclase decide *dónde* va la auth sin un solo `if` por tipo (polimorfismo).
- **`HFClient(BaseAPI)`** (`backend/integrations/nlp/`): `classify(text, model)` hace POST y normaliza a `{label, score}` (clase ganadora) con parseo defensivo.
- **CI:** `HF_TOKEN: dummy` añadido al workflow (la nueva key obligatoria rompería el fail-fast de `Settings` en CI).

**Motivo del cambio de endpoint:** el endpoint clásico `api-inference.huggingface.co` está **deprecado** (ni resuelve DNS). Se migró al router del provider serverless: `https://router.huggingface.co/hf-inference/models/{model}`. *(De paso se detectó que WSL2 no tiene salida IPv6 — gotcha latente del entorno.)*

### E3-02 · Detección de clickbait con zero-shot — decisión

**Restricción descubierta probando:** el serverless `hf-inference` **no sirve ningún modelo de clickbait específico** — sondeados `elozano/bert-base-cased-clickbait-news`, `valurank/distilroberta-clickbait` y `Stremie/bert-base-uncased-clickbait-detection`, todos devuelven `400 "Model not supported by provider"`. El `cross-encoder/nli-deberta-v3-small` de la tabla **tampoco** está servido.

Lo **único** viable para clickbait en remoto es **zero-shot vía `facebook/bart-large-mnli`** (confirmado servido; discrimina bien, ver ejemplo arriba).

**Decisión:** zero-shot remoto con `bart-large-mnli` para el MVP. Definimos nosotros las etiquetas (`["clickbait", "factual"]`) y dejamos `elozano` (modelo dedicado, más preciso) como **mejora futura** en backend local, si llega la infra.

**Implicación de código:** la respuesta zero-shot del router es una **lista plana** `[{label, score}, ...]` (ordenada), distinta del text-classification `[[...]]`. Por eso `classify` (que normaliza `data[0][0]`) **no sirve** tal cual: E3-02 añade una **variante `zero_shot(text, labels)`** que envía `parameters.candidate_labels` y normaliza `data[0]`.

### E3-03 · Análisis de sentimiento — decisión

Tool `analyze_sentiment(text)` que **reutiliza `classify`** (es *text-classification*, no necesita variante nueva) sobre `cardiffnlp/twitter-roberta-base-sentiment-latest`.

**Por qué `cardiffnlp` (3 vías) y no `distilbert` (binario):** en titulares de noticias el **neutral** es frecuente (enunciados factuales); forzarlos a *positive/negative* distorsiona. cardiffnlp clasifica en `positive` / `neutral` / `negative`. Verificado: *"The committee will meet on Tuesday"* → `neutral` (0.94). Ambos están servidos en remoto; `distilbert` quedaría como opción si se priorizara latencia.

> **Fiabilidad:** la inferencia remota da *timeouts* puntuales (HF); el cliente ya los reporta como `ToolResult.fail("Request timed out.")`. El reintento queda como mejora futura.

### E3-04 · Tests NLP

`tests/test_nlp.py` con **respx** (mockeando el `POST` al router de HF), cubriendo las dos formas de respuesta:

- **`classify`:** etiqueta ganadora `data[0][0]`; forma inesperada → `fail` (no excepción); HTTP `503` → propaga el error.
- **`zero_shot`:** etiqueta ganadora `data[0]`, y que la petición incluye `parameters.candidate_labels`.
- Que la petición lleva el header `Authorization: Bearer` (cubre `_apply_auth`).
- **Integration** (marcados `@pytest.mark.integration`): llamadas reales a `classify` y `zero_shot` que validan el contrato `{label, score}`, fuera de la CI.

Cierra la **Épica 3** (las 2 tools núcleo —clickbait y sentimiento— sobre el cliente HF, con tests).

## Épica 4 — Validación E2E del MVP

> Smoke test E2E del MVP OK (2026-06-03): `health_check` → `get_nyt_news` → `detect_clickbait`/`analyze_sentiment`, encadenado por el protocolo MCP real. Titulares del NYT salen `factual` (sin sobre-marcar; el *listicle* fue el de menor confianza factual); sentiment 3-vías discrimina bien. Dos hallazgos → issues **#44** (escenarios/evidencias) y **#45** (fiabilidad).

### E4-01 · Escenarios E2E + evidencias

Desde un cliente MCP real, el LLM **orquesta** las tools para resolver la petición del usuario. Escenarios que soporta el MVP:

| # | Escenario | Tools que encadena el LLM |
| :--- | :--- | :--- |
| 1 | **Flujo estrella:** "titulares del NYT sobre `<tema>` → ¿cuáles son clickbait?" | `get_nyt_news` / `get_guardian_news` → `detect_clickbait` |
| 2 | "¿qué tono tienen esos titulares?" | `analyze_sentiment` |
| 3 | Estado del servidor y sus integraciones | `health_check` |
| 4 | Tema inexistente → mensaje claro, sin excepción | `get_*_news` (rama de error) |

**Evidencia — smoke test E2E (2026-06-03)**, ejecutado por el protocolo MCP real (`health_check` → `get_nyt_news` → NLP):

| Titular (NYT real) | `detect_clickbait` | `analyze_sentiment` |
| :--- | :--- | :--- |
| 5 Things to Know About Nithya Raman | factual **0.74** | — |
| Scientists Find Way to Supercharge Dangerous Computer Worms With A.I. | factual 0.80 | — |
| Political Newcomer Beats Trump-Backed Candidate in Iowa Governor Primary | factual 0.83 | `neutral` 0.86 |
| U.S. Treasury Imposes Sanctions on Iran's Biggest Crypto Exchange | factual 0.88 | — |
| Trump Has Failed as Commander in Chief | — | `negative` 0.91 |

Conclusiones:
- **Sin sobre-marcar:** los titulares del NYT (fuente reputada) salen `factual`; el *listicle* "5 Things to Know…" es el de **menor** confianza factual (0.74) — el modelo capta el estilo. Que sí marca clickbait se validó aparte ("You will not believe…" → `clickbait` 0.79).
- **Sentiment de 3 vías** discrimina bien (opinión → `negative` 0.91; noticia → `neutral` 0.86).
- **Fiabilidad:** 1 de 5 llamadas NLP dio *timeout* → motivó **E4-02** (reintento).
- **Limitación:** con 2 fuentes reputadas (NYT/Guardian) apenas aparece clickbait; evaluarlo de verdad pide una fuente/dataset sensacionalista (E4-03, aparcado).

> Las capturas desde Claude Desktop se adjuntan en la memoria del TFG; esta tabla es la transcripción de la validación in-session.

### E4-02 · Reintento ante fallos transitorios de HF

El smoke test confirmó que la inferencia remota de HF falla de forma **transitoria** (~1 de cada 5 llamadas dio *timeout*; recurrente durante E3). Se añadió un **reintento** en `BaseAPI.make_request`:

- **Opt-in por clase:** `MAX_RETRIES` (default `0` → Guardian/NYT no reintentan) y `RETRY_BACKOFF`. `HFClient` lo activa con `MAX_RETRIES = 3`.
- **Solo transitorios:** `httpx.TimeoutException` y HTTP `503`; cualquier otro error falla al instante (reintentar no lo arregla).
- **Tests (`respx`):** `503→200` y `timeout→200` (recupera al reintentar), y `503` perpetuo → agota reintentos (`MAX_RETRIES + 1` intentos). Usan `RETRY_BACKOFF = 0` para no esperar de verdad.

Motivo: mejorar la fiabilidad del MVP frente a la *flakiness* del backend remoto, sin romper el contrato (sigue devolviendo `ToolResult.fail` si se agotan los reintentos).

### E4-04 · Ajustes de tools tras validación E2E

La validación destapó tres problemas al buscar por tema (p.ej. "artificial intelligence"), todos corregidos:

- **NYT — relevancia:** el cliente forzaba `sort=newest`, que hacía que `q` **no filtrara** (devolvía lo más nuevo sin relación). Ahora `sort = "relevance" if topic else "newest"`. *(Verificado: devuelve IA limpia.)*
- **Guardian — precisión:** el `q` libre matchea palabras sueltas ("intelligence" arrastraba espías/música). Ahora filtra por **tag** curado: `/tags?q=<topic>` → top tag → `/search?tag=<id>`, con **fallback** a `q` si no hay tag.
- **Usabilidad del LLM:** `topic` no tenía `description` en el schema (solo en el docstring), así que el LLM a veces inventaba parámetros (`query`). Ahora usa `Field(description=…)` en ambas tools.

**Lección de la validación:** fueron un bug de **comportamiento de API externa** (NYT `sort`) y uno de **precisión de búsqueda** (Guardian) que un test **mockeado no destapa** — solo la llamada real. La validación garantiza *forma*, no *corrección*; por eso aquí pesa la verificación empírica/integración.

Tests (`respx`): NYT manda `sort=relevance`/`newest` según haya topic; Guardian usa `tag` o cae a `q`.

### Rate limiting, tracking de llamadas y cuota — R2.4 / R2.6 / R2.7 (issue #50)

Endurecimiento del `API_Consumer` en `BaseAPI`, heredado por los tres clientes (NYT, Guardian, HF):

- **R2.4 · Rate limiting** — `AsyncLimiter` (*token bucket*) **por instancia**, configurable por clase con `RATE_CALLS` / `RATE_PERIOD`. Límites reales: NYT `5/60s`, Guardian `60/60s`. Es **por instancia** (no atributo de clase compartido) para que cada cliente tenga su propio cupo y no se pisen entre ellos.
- **R2.6 · Tracking** — `call_count` cuenta **cada intento real** a la API (incluidos los reintentos de E4-02). Property de solo lectura.
- **R2.7 · Cuota restante** — `remaining_quota`, resuelta de forma **híbrida** según lo que cada API expone (polimorfismo con el hook `_read_quota`):
  - **Guardian** lee el header real `x-ratelimit-remaining-day`.
  - **NYT** no manda headers → la **deriva**: `DAILY_LIMIT − call_count` (con `DAILY_LIMIT = 500`).

**Decisión de diseño — observabilidad, no payload.** R2.6/R2.7 se redactaron como "devolver/mostrar al usuario", pero meter el uso de API en la salida de cada tool **ensucia** la respuesta que lee el consumidor/LLM. Se expone como **observabilidad interna**: un evento estructurado `api.call` (`structlog` → stderr) con `api`, `endpoint`, `call_count` y `remaining_quota` en cada llamada exitosa. El requisito se ajustó en consecuencia (registrado en la memoria de cambios del TFG).

Tests (`respx`): NYT deriva `DAILY_LIMIT − call_count`; Guardian lee la cuota del header; ambos cuentan llamadas (Guardian: **2** por búsqueda con `topic`, por el `/tags` + `/search`).

> **Aislamiento de tests:** emitir el log `api.call` destapó un bug latente — `test_logging.py` configuraba structlog **global** apuntando al `stderr` temporal de `capsys`; al cerrarse ese buffer, cualquier test posterior que logueara petaba con `ValueError: I/O operation on closed file`. Se añadió `tests/conftest.py` con un fixture `autouse` que **resetea structlog tras cada test** (un fallo de logging quedaba además enmascarado por el `except Exception` de `make_request` como "No articles found" — doble disfraz).

**Limitación conocida (follow-up):** `GuardianAPI._find_tag` coge `tags[0]`, y para temas que son una **sección** ("technology") Guardian lista antes tags de **nicho** (`sustainable-business/technology`) que, combinados con el filtro `from-date`, dan **0 resultados recientes**; el tag canónico (`technology/technology`) queda más abajo. Pendiente afinar la selección de tag (preferir el canónico `X/X`, o *fallback* a `q` si el tag da 0 resultados).