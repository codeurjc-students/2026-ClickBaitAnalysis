# Estructura del repositorio

> Documento vivo. Dice **qué contiene cada carpeta** y, sobre todo, **qué
> cualifica a una pieza para vivir en ella**. Para la arquitectura en ejecución
> ver [`arquitectura.md`](arquitectura.md); para los criterios de aceptación,
> [`requisitos.md`](requisitos.md).

## Por qué criterios y no descripciones

Una descripción se escribe mirando lo que ya hay dentro, así que **por
construcción lo legitima**. «`api/` contiene endpoints, esquemas y la
orquestación del análisis» es una descripción cierta que habría dado por bueno
que la lógica de veredictos viviera ahí — y esa ubicación resultó tener una
consecuencia seria (ver [tensión 1](#1--la-orquestación-del-análisis-en-api)).

Un **criterio** es distinto: es una pregunta que se contesta sí o no sobre una
pieza concreta, y puede delatar a algo que ya está dentro. Por eso cada carpeta
declara tres cosas:

1. **Contiene** — qué hay hoy.
2. **Criterio** — la pregunta que decide si algo pertenece aquí.
3. **No va aquí aunque lo parezca** — el caso concreto que se presta a confusión.

---

## `backend/analysis/`

**Contiene** — la lógica del dominio del clickbait: el vocabulario del análisis y
la orquestación que contrasta las señales.

**Criterio** — *si borraras la API REST y el servidor MCP y dejaras sólo una
función de Python que analiza titulares, ¿esto seguiría haciendo falta?* Si la
respuesta es **sí**, va aquí.

**No va aquí aunque lo parezca** — nada que describa **cómo se sirve** el
análisis: servidores, herramientas del catálogo, peticiones o historial. Eso es
sistema y vive en `api/schemas.py`.

**La regla que lo mantiene honesto**: `api/` puede importar de aquí, **nunca al
revés**. El dominio no sabe que lo están sirviendo, y por eso puede servirse
también por MCP. El día que este paquete necesite importar de `api/`, algo está
mal colocado — es una alarma, no una opinión.

| Fichero | Qué hace |
|---|---|
| `domain.py` | El vocabulario: `Dimension`, `SignalType`, `SignalStatus`, `SignalResult`, `DimensionVerdict`, `OverallVerdict`, `AnalyzeRequest/Response` |
| `orchestrator.py` | Lanza las señales en paralelo, las agrupa por dimensión y deriva el veredicto con jerarquía explícita |
| `tool.py` | Registra `analyze_headline` como herramienta MCP. Vive aquí y no en `integrations/nlp/tool.py` porque allí sería un ciclo |

Nació al comprobar que la orquestación estaba en `backend/api/analyze.py`, donde
no le correspondía —estaba ahí porque era donde hizo falta primero—. La
consecuencia no era estética: el servidor MCP no exponía nada que contrastara
señales, así que **el agente conversacional no podía reproducir el veredicto del
formulario**. Ninguna carpeta existente lo admitía, y sus propios criterios lo
decían: `api/` sí existiría sin HTTP, `core/` no puede saber de clickbait,
`integrations/` no envuelve nada. Los criterios pidieron un paquete nuevo.

## `backend/api/`

**Contiene** — la aplicación FastAPI: rutas, contrato y las piezas que sólo
existen para servirlo.

**Criterio** — *¿existiría esto si el sistema no expusiera HTTP?* Si la respuesta
es **sí**, no va aquí.

**No va aquí aunque lo parezca** — la lógica que decide **qué significa** un
análisis. Que el veredicto se calcule al atender un `POST` es una coincidencia
de historia, no una propiedad suya.

| Fichero | Qué hace |
|---|---|
| `app.py` | La aplicación y sus cinco rutas. Segundo punto de entrada del backend, hermano de `main.py` y no capa sobre él |
| `schemas.py` | El contrato: lo que entra y sale por HTTP, y los enums que lo acompañan |
| `catalog.py` | Construye el catálogo agregando el `list_tools` de cada servidor MCP — `GET /tools` |
| `execute.py` | Valida los argumentos contra el `inputSchema` e invoca — `POST /tools/{name}/execute` |
| `mcp_session.py` | Abre sesiones MCP. Es donde la API actúa como **cliente**, no como servidor |
| `history.py` | Almacén del historial sobre SQLite — ⚠️ [tensión 2](#2--el-almacén-del-historial-en-api) |

`/analyze` ya no orquesta nada: llama a `backend/analysis/orchestrator.py` y se
limita a servir el resultado. `schemas.py` importa de allí los tipos del dominio
que necesita —`Dimension` y `SignalType`, para `ToolModelCard`— en la única
dirección permitida.

## `backend/core/`

**Contiene** — maquinaria compartida por varias capas.

**Criterio** — *¿lo usa más de una capa **y** no sabe nada del dominio del
clickbait?*

**No va aquí aunque lo parezca** — nada que conozca titulares, señales,
dimensiones o veredictos, por muy reutilizable que sea. Reutilizable no es lo
mismo que genérico.

| Fichero | Qué hace |
|---|---|
| `base_api.py` | `BaseAPI`: rate-limit, reintentos, cuota, autenticación y el log `api.call`. Lo heredan todos los clientes |
| `models.py` | `ToolResult`, el modelo de retorno que viaja **dentro** del proceso (no por MCP) |
| `logging.py` | `configure_logging()` — structlog, en consola o JSON |
| `observability.py` | `log_tool_invocation`, el decorador que registra cada invocación con parámetros y duración |
| `health.py` | `check_health()` y su registro como tool MCP — ⚠️ [tensión 4](#4--health-conoce-mcp-desde-core) |

## `backend/integrations/`

**Contiene** — un paquete por cada cosa externa que el sistema envuelve.

**Criterio** — *¿envuelve algo **externo al proyecto**: una API, un modelo, un
dataset?*

**No va aquí aunque lo parezca** — la maquinaria que **descubre** o **describe**
las integraciones. Esa opera *sobre* ellas, no *es* una.

Cada integración repite el mismo patrón, y esa repetición es deliberada: hace la
estructura predecible y es lo que permite el descubrimiento automático.

| | |
|---|---|
| `<nombre>/client.py` | La lógica de la API. Hereda `BaseAPI` |
| `<nombre>/tool.py` | Capa fina que declara la herramienta MCP y delega en el cliente |

| Fichero | Qué hace |
|---|---|
| `discovery.py` | Recorre el paquete y registra lo que encuentra — ⚠️ [tensión 3](#3--discovery-y-metadata-no-envuelven-nada) |
| `metadata.py` | La categoría y procedencia que cada tool declara, para el catálogo — ⚠️ [tensión 3](#3--discovery-y-metadata-no-envuelven-nada) |
| `guardian/`, `nyt/` | Fuentes de noticias |
| `weather/` | Fuente meteorológica. Sobrevive de la Épica 0 y sirve de contraste: es la única que no tiene nada que ver con el clickbait |

### `backend/integrations/nlp/`

El paquete más grande, porque contiene **las señales** — el núcleo del detector.

| Fichero | Qué hace |
|---|---|
| `base.py` | `NLPBackend` (ABC): la interfaz que cumplen el backend remoto y el local |
| `client.py` | `HFClient(BaseAPI, NLPBackend)`: backend remoto contra HuggingFace |
| `local.py` | Backend local con `transformers`. Cachea los pipelines por `(tarea, modelo)` para no recargar, e **importa `transformers` de forma perezosa** — por eso el módulo se puede importar sin torch, que es lo que permite el CI ligero. Las inferencias van a un hilo aparte porque bloquean |
| `factory.py` | `get_nlp_backend()`: elige uno según `settings`. Es lo que permitió cambiar de remoto a local sin tocar ninguna señal |
| `lexical.py` | Señal **interpretable**. Busca tres tipos de pista —palabras, frases y patrones regex— y devuelve cada coincidencia **con su posición** (`span`), que es lo que permite resaltar los cues sobre el titular. Clickbait si el recuento llega a `THRESHOLD` |
| `linear.py` | Señal **interpretable**: regresión logística sobre los cues, con los pesos visibles y las contribuciones de cada rasgo en la salida. Carga los pesos de `linear_clickbait.json` — ⚠️ [bug 1](#1--linearpy-lee-el-fichero-de-pesos-al-importar) · [bug 2](#2--dos-señales-de-forma-comparten-extracción-de-rasgos) |
| `incoherence.py` | Señal **híbrida**: decisión transparente (umbral sobre la similitud) con rasgo opaco (embeddings). Codifica titular y cuerpo con `all-MiniLM-L6-v2` y los compara por **similitud coseno**: incoherente si baja de 0,3. El modelo se carga una sola vez y de forma perezosa, de ahí los ~20 s de la primera llamada |
| `model_cards.py` | Ficha de cada señal: tipo, dimensión que mide y límites medidos |
| `outputs.py` | Los `TypedDict` de retorno, para que MCP publique el `outputSchema` |
| `tool.py` | Registra las señales como herramientas MCP |
| `cues/` | Las listas de *cues* léxicos, en ficheros de datos |

## `backend/config/`

**Contiene** — `settings.py`, y sólo eso.

**Criterio** — *¿es un valor que cambia entre entornos sin tocar código?*

**No va aquí aunque lo parezca** — los umbrales de decisión de una señal. Ésos
son parte del modelo y viven con él, aunque sean números configurables.

## `backend/evaluation/`

**Contiene** — los guiones de evaluación offline.

**Criterio** — *¿se ejecuta **a mano** para producir una medición, y no forma
parte de ningún servicio en marcha?*

**No va aquí aunque lo parezca** — nada que se importe en tiempo de ejecución.
Si un endpoint o una tool lo necesita, es que no era evaluación.

| Fichero | Qué hace |
|---|---|
| `splits.py` | Split físico train/dev/test, congelado (#72) |
| `eval_lexical.py` | Baseline del léxico: carga, puntúa, matriz de confusión, barrido de umbral |
| `linear_model.py` | **Entrena** el modelo lineal y serializa los pesos a `linear_clickbait.json`, que es lo que consume la señal en ejecución; compara además contra el baseline de reglas. El nombre engaña: no contiene el modelo, lo produce — ver [renombrados](#renombrados-propuestos). Arrastra además un `featurize()` **sin ningún llamante** |
| `eval_external.py` | Validación externa sobre Webis-17 (#76) — la que destapó el sesgo de fuente |

## `backend/main.py`

Punto de entrada del **servidor MCP**. Registra las integraciones descubiertas
más el chequeo de salud, y arranca con el transporte configurado. No contiene
lógica: si algo se le añadiera, pertenece a otro sitio.

---

## Fuera de `backend/`

| Carpeta | Criterio |
|---|---|
| `tests/` | Espeja `backend/`: un fichero por módulo, misma ruta relativa |
| `spikes/` | ¿Es código **desechable**, escrito para responder **una** pregunta? Lleva sus resultados en la cabecera y está excluido de ruff a propósito |
| `docs/` | Documentación y sus fuentes (`.drawio`, `img/`) |
| `data/` | **Versionado e inmutable**: datasets y splits congelados. Si algo cambia en ejecución, no va aquí |
| `var/` | **Gitignored y mutable**: estado que cambia en cada petición. Es el directorio que se monta como volumen |
| `docker/` | *(vacía)* — reservada para H4 |
| `frontend/` | *(vacía)* — reservada para la SPA Angular |

---

## Tensiones detectadas

Piezas que **no cumplen el criterio de la carpeta donde están**. Se documentan,
no se resuelven aquí: convertir este fichero en un refactor encubierto es cómo se
queda a medias.

### 1 · La orquestación del análisis, en `api/` — ✅ RESUELTA (#107)

`backend/api/analyze.py` contrastaba las señales desde la capa REST, lo que
**seguiría teniendo sentido en un sistema sólo-MCP** e incumplía el criterio de
`api/`. La consecuencia no era estética: el servidor MCP no exponía ninguna
herramienta que contrastara señales, así que el agente conversacional de R13 no
podía reproducir el veredicto del formulario.

Resuelta moviéndola a [`backend/analysis/`](#backendanalysis) y exponiéndola como
la tool MCP `analyze_headline`. **Las dos fachadas comparten ahora la misma
implementación**, y hay un test que lo fija:

```python
assert analysis_tool.analyze is orchestrator.analyze
```

Fue además la primera vez que los criterios de este documento se usaron para
decidir en vez de para describir: las tres carpetas existentes rechazaron la
pieza por su propio criterio, y eso es lo que pidió el paquete nuevo.

### 2 · El almacén del historial, en `api/`

`backend/api/history.py` está ahí porque su consumidor es `GET /history` — que
es exactamente el argumento que falló con `analyze.py`.

¿Querría un servidor MCP guardar historial de lo que ejecutó? Probablemente sí.
Si la respuesta es sí, el módulo incumple el criterio igual que el anterior, sólo
que todavía sin consecuencia visible.

### 3 · `discovery` y `metadata` no envuelven nada

Ninguno de los dos envuelve una API, un modelo ni un dataset: son la maquinaria
que **descubre** y **describe** las integraciones. Cumplen el criterio de `core/`
—maquinaria compartida, sin dominio— mejor que el de `integrations/`.

A favor de dejarlos donde están: operan sobre ese paquete y viven a su lado. En
contra: por esa regla, cualquier cosa que opere sobre algo debería vivir dentro.

### 4 · `health` conoce MCP desde `core/` — ✅ con regla (#107)

`backend/core/health.py` es infraestructura —sondea APIs externas, no sabe nada
de clickbait— pero además **se registra como herramienta MCP**, así que conoce
FastMCP desde el núcleo. Parecía una excepción incómoda.

Al resolver la tensión 1 apareció el mismo caso por segunda vez —
`analysis/tool.py` también se registra desde fuera de `integrations/`, porque
hacerlo desde `nlp/tool.py` sería un ciclo— y dos casos ya no son una excepción,
son un patrón. Queda declarado así:

> **`discover_and_register` encuentra las INTEGRACIONES. Lo que no es una
> integración —la salud, el análisis— se registra explícitamente desde
> `main.py`.**

Con eso, un módulo puede exponerse como herramienta sin dejar de pertenecer a su
capa: lo que importa es **quién decide registrarlo**, y esa decisión vive en el
punto de entrada, no repartida por el árbol.

---

## Bugs detectados

Al leer los módulos para escribir las descripciones de arriba salieron dos cosas
que sí hay que arreglar. **No son de la misma clase**, y conviene no meterlas en
el mismo saco.

### 1 · `linear.py` lee el fichero de pesos al importar

```python
JSON_FILE = Path(__file__).resolve().parent / "linear_clickbait.json"
with open(JSON_FILE, encoding="utf-8") as f:  # ← nivel de módulo
    JSON = json.load(f)
```

Es un efecto colateral en tiempo de import: **importar el módulo abre y parsea un
fichero**, y falla si no está. Hoy funciona porque el JSON está commiteado, pero
un import no debería tocar el disco — cualquier cosa que importe la señal, aunque
sea para inspeccionarla, paga esa lectura y hereda ese modo de fallo.

Arreglo: carga perezosa, como ya hacen `local.py` con `transformers` e
`incoherence.py` con el modelo de embeddings. El patrón ya está en la casa.

### 2 · Dos señales de **forma** comparten extracción de rasgos

`featurize_cues()` en `linear.py` llama a `lexical.detect()` y reutiliza sus
listas: la señal lineal está construida sobre la léxica.

**Esto ya está declarado**, y conviene decirlo antes que nada. La ficha de
`detect_clickbait_linear` lo recoge entre sus limitaciones:

> *«No capta engaño semántico (usa las mismas pistas de superficie que el
> léxico).»*

Así que no es un descubrimiento: es una limitación conocida y publicada, que
además viaja al frontend por `describe_models`. Lo que **no** está escrito es su
consecuencia sobre el contraste:

- Si una lista de cues tiene un hueco, **las dos señales lo tienen igual**; si un
  cue salta por error, las dos lo ven. **Dos señales de forma de acuerdo no son
  dos confirmaciones independientes.**
- Lo que sí queda de contraste: pueden discrepar en *cuánto pesa* lo encontrado
  —una cuenta plano contra umbral, la otra pondera con pesos aprendidos— pero no
  en *qué se ha encontrado*.

Y lo que **no** está afectado: `incoherence.py` parte de otra entrada —el cuerpo
de la noticia— así que la dimensión de **engaño** es independiente de la de
forma. La dependencia vive dentro de una sola dimensión, y el docstring de
`model_cards.py` ya avisa de lo relacionado: *«tres señales de forma de acuerdo
no significan que el titular engañe»*.

No es un arreglo de código. Es **medirlo y añadir la consecuencia a la ficha**:
la correlación entre las dos señales sobre el split de dev convierte «comparten
rasgos» en un número, que es lo que el proyecto hace con el resto de sus límites.

## Renombrados propuestos

Criterio: **renombrar cuando el nombre hace una predicción falsa**, no cuando es
escueto. `base.py` es escueto y predice bien; `linear_model.py` predice «aquí
vive el modelo lineal» y es mentira.

| Fichero | Propuesta | Por qué |
|---|---|---|
| `evaluation/linear_model.py` | `train_linear.py` | No contiene el modelo: lo **entrena**. El modelo vive en `nlp/linear.py` + el JSON. Y colisiona de un vistazo con `nlp/linear.py`, que sí es la señal. Encaja además con sus hermanos, ya verbo+objeto: `eval_lexical`, `eval_external` |
| `nlp/client.py` | `remote.py` | El par actual `client.py` / `local.py` no dice que sean **dos implementaciones de la misma interfaz**; `remote.py` / `local.py` sí. Y en las demás integraciones `client.py` significa otra cosa —«el cliente de esta API»—, así que además es inconsistente entre paquetes |
| `integrations/metadata.py` | `tool_metadata.py` | Menor: «metadata» de qué. El docstring ya lo cubre |

No se renombran `base.py`, `models.py`, `outputs.py` ni `nlp/linear.py`: son
escuetos pero no engañan, y al renombrar `linear_model.py` desaparece la única
colisión real.

## Deuda: 19 módulos sin docstring

De los 30 módulos reales de `backend/`, **19 no declaran qué hacen**, y se
concentran en el código de Fase A: todo `core/`, todos los `client.py` y casi
todo `nlp/`. Lo escrito en Fase B sí está documentado.

Las descripciones de las tablas de arriba se han sacado leyendo sus definiciones,
no sus docstrings. **Lo correcto sería lo contrario**: que cada módulo declare su
propósito y que este documento se limite a los criterios y las relaciones — una
línea en un fichero central es lo primero que se queda obsoleto, un docstring
está donde se edita el código.
