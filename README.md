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


### Decisiones de diseño relevantes

| Decisión | Motivo |
|---|---|
| Schema común `{title, url, date}` entre Guardian y NYT | Permite que la futura tool MCP (E2-02) y el analizador NLP (E3) consuman datos sin ramificar lógica por fuente |
| Hereda de `BaseAPI` igual que Guardian/Weather | Reutiliza la inyección automática de `api-key`, manejo uniforme de timeout y errores HTTP; cualquier mejora futura en `BaseAPI` aplica a las tres integraciones |
