# Estructura del repositorio

> Documento vivo. Dice **qué contiene cada carpeta** y, sobre todo, **qué
> cualifica a una pieza para vivir en ella**. Para la arquitectura en ejecución
> ver [`arquitectura.md`](arquitectura.md); para los criterios de aceptación,
> [`requisitos.md`](requisitos.md).
>
> **Revisado entero contra el árbol en #173 (2026-09-23)**: cada fichero nombrado
> existe, cada fichero de las carpetas descritas está nombrado, y las
> afirmaciones sobre el código —bugs, tensiones, deuda— se han vuelto a comprobar.
> **Puesto al día en #108 (2026-09-24)**: los dos renombrados hechos, el bug 1
> cerrado y la deuda de docstrings saldada. **Y en #188 (2026-09-26)**: el
> paquete del agente, `backend/agent/`.

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

## `backend/agent/`

**Contiene** — el agente conversacional (R13, #188): el bucle que deja a un
modelo de lenguaje elegir herramientas, las ejecuta por MCP y le devuelve lo que
responden; la traza que produce, y los prompts de sistema versionados.

**Criterio** — *¿existe para que un modelo de lenguaje elija herramientas, las
ejecute y cuente lo que devuelven?* Si la respuesta es **sí**, va aquí.

**No va aquí aunque lo parezca** — los trabajos en memoria y el sondeo de
`/chat`, que son de `api/` porque sin HTTP no existirían (#189); el cliente del
modelo, que envuelve algo externo y vive en `integrations/llm/`; y el veredicto,
que es de `analysis/`: el agente no decide nada, narra lo que deciden las
herramientas (R13.4).

| Fichero | Qué hace |
|---|---|
| `agente.py` | `responder()`, el bucle, con una `Configuracion` —backend, servidores, prompt, cortes, seis vueltas y `think`— que **recibe** en vez de leer `settings` (#119; lo vigila `tests/test_arquitectura.py`, sin ninguna excepción). Descubre el catálogo una vez por consulta, ejecuta cada herramienta en el servidor que la publicó, y un error de una herramienta vuelve al modelo como resultado. Razona siempre (`think=True`): sin razonar, el 27B se inventaba los resultados de las herramientas (#188) |
| `traza.py` | Los tipos de lo que produce: cada vuelta del modelo, con sus medidas, y cada llamada, con su resultado **entero**, que es de donde salen las tarjetas; y cómo terminó. Aparte del bucle para que la API los importe sin él, y con las claves en inglés porque irán al contrato (#189) |
| `prompts.py` y `prompts/` | Los prompts de sistema versionados (R13.5). Salen del spike #82 con una corrección: los dos llamaban «zero-shot» a `detect_clickbait` |

Es un paquete de **primer nivel**, hermano de `analysis/`, porque los criterios
de las otras carpetas lo rechazan: **conoce el dominio** —el prompt dice qué es
cada señal—, así que no cabe en `core/`; y **no envuelve nada externo**, así que
no es una integración. Como `analysis/`, no importa de `api/`.

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
| `app.py` | La aplicación y sus seis rutas. Segundo punto de entrada del backend, hermano de `main.py` y no capa sobre él |
| `schemas.py` | El contrato: lo que entra y sale por HTTP, y los enums que lo acompañan |
| `catalog.py` | **Traduce** el descubrimiento al contrato del catálogo — `GET /tools` |
| `execute.py` | **Traduce** una invocación a su código de estado — `POST /tools/{name}/execute` |
| `history.py` | Almacén del historial sobre SQLite — ⚠️ [tensión 2](#2--el-almacén-del-historial-en-api) |
| `ratelimit.py` | Cuántas peticiones admite cada cliente y qué se le responde si se pasa (R12.4, #169). Está aquí, y no en `core/`, porque todo lo suyo es HTTP: códigos de estado, cabeceras y rutas. El MCP no lo usa |
| `export_openapi.py` | Vuelca el contrato OpenAPI a `frontend/openapi.json`, del que se genera el cliente tipado del frontend (`npm run gen:api`). Importa la app en vez de pedirle `/openapi.json` a un servidor, y el JSON **se commitea** para que una PR enseñe qué cambió del contrato; `test_el_contrato_commiteado_esta_al_dia` vigila que no se quede atrás. Está aquí porque sin HTTP no existiría |

Desde #137 `catalog.py` y `execute.py` son **traductores**: descubrir e invocar
viven en `core/mcp/`, porque el agente de R13 necesita ese mecanismo y no puede
importar de una fachada. Lo que queda aquí es lo que sólo tiene sentido por HTTP
—los cuatro finales de `/execute` y sus códigos, el `ServerStatus` del
catálogo— más la ficha de modelo de cada señal, que es lo único de esto que
conoce el dominio.

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
| `errores.py` | `describir_error()`: cómo se describe un error en una **salida pública** —código HTTP o nombre del tipo, nunca el texto de la librería, que llegó a publicar una clave de API (#163)—. Abre los `ExceptionGroup` del cliente MCP (#164). La usan `health.py` y `api/catalog.py`: dos capas, y ningún conocimiento del clickbait. Desde #188 también el agente, que publica los errores de las herramientas en la traza |
| `texto.py` | `TextoOpcional`: un `str \| None` que convierte en `None` la ausencia escrita como texto —vacío, en blanco, o sólo «None» o «null»— sin cambiar el esquema publicado (#197). Existe porque un modelo de lenguaje escribe la ausencia en vez de omitir el parámetro: el agente mandó `content="None"` y la incoherencia lo comparó con el titular. Lo usan `analysis/domain.py` y las herramientas de noticias; `es_ausente`, además, la de incoherencia, que exige el cuerpo |
| `mcp/session.py` | Abre sesiones MCP. Es donde el sistema actúa como **cliente**, no como servidor |
| `mcp/tools.py` | Descubre e invoca herramientas, devolviendo un resultado neutro |

`mcp/` llegó aquí en #137 desde `api/`, y el criterio lo decide sin empate: no
envuelve nada externo —los servidores MCP son nuestros— y lo usan dos capas, la
API REST hoy y el agente de R13 mañana. Es el mismo razonamiento de la
[tensión 3](#3--discovery-y-metadata-no-envuelven-nada), aplicado a un caso que
sí tenía que moverse: allí `discovery` y `metadata` se quedan donde están porque
nada rompe; aquí el agente no podía importar de una fachada sin que fallara
`tests/test_arquitectura.py`.

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

**Una integración puede no publicar herramientas.** `llm/` envuelve el servidor
de modelos y lo consume el agente por dentro, sin ofrecerlo al catálogo, así que
no tiene `tool.py` (#187). El patrón de arriba es el de las integraciones que
**se sirven**; las que sólo **se usan** no lo necesitan.

| Fichero | Qué hace |
|---|---|
| `discovery.py` | Recorre el paquete y registra lo que encuentra. Un paquete sin módulo `tool` va a `without_tools`, no a `failed`: no publicar herramientas no es estar roto, y lo que cae en `failed` se anuncia al arrancar como integración rota (#187) — ⚠️ [tensión 3](#3--discovery-y-metadata-no-envuelven-nada) |
| `metadata.py` | La categoría y procedencia que cada tool declara, para el catálogo — ⚠️ [tensión 3](#3--discovery-y-metadata-no-envuelven-nada) |
| `guardian/`, `nyt/` | Fuentes de noticias |
| `weather/` | Fuente meteorológica. Sobrevive de la Épica 0 y sirve de contraste: es la única que no tiene nada que ver con el clickbait |

### `backend/integrations/nlp/`

El paquete más grande, porque contiene **las señales** — el núcleo del detector.

| Fichero | Qué hace |
|---|---|
| `base.py` | `NLPBackend` (ABC): la interfaz que cumplen el backend remoto y el local |
| `remote.py` | `HFClient(BaseAPI, NLPBackend)`: backend remoto contra HuggingFace. Se llamaba `client.py` hasta #108: el par `remote.py` / `local.py` dice que son dos implementaciones de la misma interfaz |
| `local.py` | Backend local con `transformers`. Cachea los pipelines por `(tarea, modelo)` para no recargar, e **importa `transformers` de forma perezosa** — por eso el módulo se puede importar sin torch, que es lo que permite el CI ligero. Las inferencias van a un hilo aparte porque bloquean |
| `factory.py` | **Qué hay configurado de verdad**: qué backend (`get_nlp_backend`), qué modelo ejecuta cada señal (`get_model_id`) y qué ficha se publica (`ficha_efectiva`). Con `remote.py` es el ÚNICO de esta capa al que se le permite leer `settings`, y de ahí sale la forma de todo lo demás: los detectores no resuelven su configuración, la **reciben**. Cachea las instancias **por el valor del setting**, que es lo que arregla el congelado al importar de #87 sin perder la reutilización |
| `dependencias.py` | Pregunta si `torch` o `sentence-transformers` están instalados —con `find_spec`, **sin importarlos**, para no deshacer los imports perezosos de arriba— y produce el mensaje que se enseña cuando faltan. Existe porque `requirements.txt` **no los trae a propósito**, así que faltar es el estado normal y no una avería. Desde #162 responde también por los **modelos**: con la descarga desactivada, uno puesto por `NLP_MODELS` no está en la imagen, y eso tampoco es una avería — aunque aquí no se puede preguntar antes, y se reconoce el caso por el error que lanza la librería. No envuelve nada externo, y por eso no es una integración: es un módulo de apoyo del paquete, como `base.py` o `factory.py`. No es el caso de la [tensión 3](#3--discovery-y-metadata-no-envuelven-nada), que vive en la raíz de `integrations/` y opera sobre todas |
| `lexical.py` | Señal **interpretable**. Busca tres tipos de pista —palabras, frases y patrones regex— y devuelve cada coincidencia **con su posición** (`span`), que es lo que permite resaltar los cues sobre el titular. Clickbait si el recuento llega a `THRESHOLD` |
| `linear.py` | Señal **interpretable**: regresión logística sobre los cues, con los pesos visibles y las contribuciones de cada rasgo en la salida. Lee los pesos de `linear_clickbait.json` en el primer uso, con `pesos()`, y no al importar (el [bug 1](#1--linearpy-lee-el-fichero-de-pesos-al-importar---cerrado-108), cerrado en #108) — ⚠️ [bug 2](#2--dos-señales-de-forma-comparten-extracción-de-rasgos---medido-109) |
| `incoherence.py` | Señal **híbrida**: decisión transparente (umbral sobre la similitud) con rasgo opaco (embeddings). Codifica titular y cuerpo con `all-MiniLM-L6-v2` y los compara por **similitud coseno**: incoherente si baja de 0,3. El modelo se carga una sola vez y de forma perezosa, de ahí los ~20 s de la primera llamada |
| `dedicated.py` | Señal **opaca**: el RoBERTa dedicado (`Stremie/roberta-base-clickbait`, #115), que sustituyó al zero-shot elegido por eliminación en E3-02 y que acertaba el 63,7 % (#109). Tiene módulo propio porque sin él su id y sus etiquetas se duplicaban entre las dos fachadas (#116). Recibe el backend y el id en vez de resolverlos (#119) |
| `model_cards.py` | Ficha de cada señal: tipo, dimensión que mide y límites medidos |
| `outputs.py` | Los `TypedDict` de retorno, para que MCP publique el `outputSchema` |
| `tool.py` | Registra las señales como herramientas MCP |
| `cues/` | Las listas de *cues* léxicos, en ficheros de datos |

### `backend/integrations/llm/`

El modelo de lenguaje del agente (#187, R13.6). Sigue el patrón de `nlp/` —una
interfaz, sus implementaciones y una factoría que es la única que lee `settings`,
lo que vigila `tests/test_arquitectura.py`—, y no publica herramientas: lo
consume el agente.

| Fichero | Qué hace |
|---|---|
| `base.py` | `LLMBackend` (ABC), con `chat()` y `disponibilidad()`, y los tipos **neutrales** de la conversación: mensaje, herramienta, llamada, respuesta con sus medidas. No son el formato de Ollama, para que otro proveedor no toque el agente; las claves van en inglés, como las del dominio (#134) |
| `ollama.py` | `OllamaClient(BaseAPI, LLMBackend)`. El chat pasa por `make_request`, sin reintentos; la disponibilidad va con `httpx` directo, porque necesita el TIPO de fallo: sólo una conexión **rechazada** es «apagado» |
| `model_card.py` | La ficha del modelo (R13.7): opaco, qué hace y qué no —el veredicto no es suyo, R13.4— y sus limitaciones medidas, cada una con su PR |
| `factory.py` | Qué hay configurado: `get_llm_backend()` —`None` si no hay agente—, `disponibilidad()` con los cuatro estados de R6.14, y `ficha_efectiva()`, que deja de publicar las medidas si se configura otro modelo (#119) |

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
| `train_linear.py` | **Entrena** el modelo lineal y serializa los pesos a `linear_clickbait.json`, que es lo que consume la señal en ejecución; compara además contra el baseline de reglas. Se llamaba `linear_model.py` hasta #108, y el nombre engañaba: no contiene el modelo, lo produce — ver [renombrados](#renombrados) |
| `eval_external.py` | Validación externa sobre Webis-17 (#76) — la que destapó el sesgo de fuente |
| `eval_acoplamiento.py` | Cuánto vale que el léxico y el lineal coincidan, si comparten los rasgos (#109) |
| `eval_featurizado.py` | Por qué coinciden: qué ve, y qué no puede ver, el vector de rasgos que comparten (#109) |
| `eval_transferencia.py` | Qué señal de forma sobrevive fuera de su dominio, con el zero-shot y un modelo dedicado de terceros (#109, #115) |
| `eval_candidatos.py` | Candidatos para sustituir al zero-shot en `forma`, con tres criterios y no sólo el acierto (#115) |
| `eval_ambiguedad.py` | El techo realista: cuánto acierta una persona contra el consenso de las demás en Webis-17 (#121) |
| `eval_incoherencia.py` | Calibra el umbral de incoherencia con método, separando cuánta información tiene la señal (AUC) de dónde se corta (#92) |
| `webis_extract.py` | Saca de los 937 MB de Webis-17 lo que sirve: los titulares, versionados en `data/external/`, y los cuerpos, regenerables, en `var/` (#121) |

## `backend/main.py`

Punto de entrada del **servidor MCP**. Registra las integraciones descubiertas y,
a mano, lo que no es una integración —el chequeo de salud y, desde #107,
`analyze_headline` (tensión 4)—; ajusta la protección contra DNS rebinding al
host en que escucha (`configurar_red`, #164: FastMCP la decide al construirse, y
dentro de compose rechazaba a la propia API); y arranca con el transporte
configurado. No contiene lógica: si algo se le añadiera, pertenece a otro sitio.

---

## Fuera de `backend/`

| Carpeta | Criterio |
|---|---|
| `tests/` | Espeja `backend/`: un fichero por módulo, misma ruta relativa. Las dos excepciones prueban el repositorio en sí, no un módulo: `test_arquitectura.py` (las reglas de importación) y `test_compose.py` (los contratos del despliegue) |
| `.github/` | ¿Lo ejecuta **GitHub**, no el sistema? `workflows/ci.yml` corre las pruebas de Python y del frontend y, desde #173, construye las dos imágenes sin publicarlas; `protect-main.yml` impide llegar a `main` si no es desde `dev`; y `medir-imagenes.yml` es el instrumento de medida de #173, que sólo se lanza a mano |
| Ficheros de la raíz | La configuración de las herramientas, en la raíz porque ahí la encuentran sin argumentos: `ruff.toml`, `pyrightconfig.json`, `pytest.ini`. Y las dependencias: `requirements.in` es lo que se declara y `requirements.txt` el lockfile que genera `pip-compile` —no se edita a mano—; `requirements-dev.txt` trae lo pesado, que el CI no instala |
| `spikes/` | ¿Es código **desechable**, escrito para responder **una** pregunta? Lleva sus resultados en la cabecera y está excluido de ruff a propósito |
| `docs/` | Documentación y sus fuentes (`.drawio`, `img/`) |
| `data/` | **Versionado e inmutable**: datasets y splits congelados. Si algo cambia en ejecución, no va aquí |
| `var/` | **Gitignored y mutable**: estado que cambia en cada petición. Es el directorio que se monta como volumen |
| `docker/` | ¿Sólo tiene sentido **dentro de una imagen**? Un `<imagen>.Dockerfile` por imagen, con su `.dockerignore` al lado y del mismo nombre; los guiones que corren **durante** el build, como `hornear_modelos.py` (#162); y la configuración que se copia **dentro** de una imagen, como el `Caddyfile` (#163). Hasta #163 la pregunta era «¿existe sólo para construir una imagen?», y el `Caddyfile` la desbordó: no construye nada, pero fuera de la imagen web no pinta nada. Tampoco cabía en `frontend/`, que es la SPA, cuando el `Caddyfile` enruta también hacia la API. El contexto del build es la raíz del repositorio, no esta carpeta. Lo de aquí puede importar de `backend/` —el horneado lee `MODEL_CARDS` para no duplicar los ids—, pero **nunca al revés**: si `backend/` o `frontend/` necesitaran algo de esta carpeta, no pertenecía aquí |
| `despliegue/` | ¿Se **instala o se ejecuta directamente en una máquina de despliegue**, fuera de toda imagen? Una subcarpeta por máquina: `maquina1/70-tunel.conf` va a `/etc/ssh/sshd_config.d/` de la de la aplicación y `maquina2/gpu-sesion` a `~/bin` de la de la GPU (#181). Su `README.md` es de operación —cómo se instala y se comprueba cada pieza—; el porqué está en el README principal. **No va aquí aunque lo parezca**: lo que entra en una imagen, que es de `docker/`; `compose.yaml`, que se queda en la raíz por lo que dice su fila; y los guiones que comprueban o miden el despliegue, como `tunel_restricciones.sh`, que son de `spikes/`: lo de aquí es lo que el sistema necesita para funcionar |
| `frontend/` | La SPA Angular. Sus criterios, abajo |
| `compose.yaml` | Un fichero, no una carpeta, pero con la misma pregunta: ¿describe cómo se levanta el sistema **entero** en una máquina? Va en la raíz y no en `docker/` porque no va dentro de ninguna imagen, y porque ahí `docker compose` lo encuentra sin `-f` (#164) |

---

## `frontend/src/app/`

**¿Habla con el backend?** → `api/`. **¿Lo usa una sola pantalla?** → su carpeta.

| Carpeta | Criterio |
|---|---|
| la raíz de `app/` | La **cáscara**, que no es de ninguna pantalla: el componente con la cabecera, la navegación y el indicador de salud (`app.ts`, `app.html` y `app.scss`, con su `app.spec.ts`), las rutas —cada pantalla se descarga perezosa con `loadComponent`— (`app.routes.ts`) y la configuración (`app.config.ts`, con `withComponentInputBinding`, que es lo que hace llegar el `:id` como `input()`) |
| `api/` | Lo que habla el contrato: el cliente generado (`schema.d.ts`), los alias con nombre corto (`models.ts`), **un servicio por familia de rutas** y lo que se lee del cuerpo de un error HTTP. No conoce el dominio: aquí no se decide qué es clickbait |
| `analisis/` | Analizar un titular y ver el resultado —también uno guardado—, con lo que sólo esa vista usa: los guardianes del `data`, el resaltado del titular, la tarjeta de señal y el vocabulario |
| `historial/` | La lista de lo anterior: filtros, paginación y el aviso de retención |
| `sistema/` | Servidores, catálogo y fichas de modelo, más el lector de esquemas que genera el formulario de cada herramienta |
| `salud/` | El indicador de salud de la cabecera (#147). **No es una pantalla**: no tiene ruta y se monta en la cáscara, porque la pregunta que responde —«¿esto falla por mí o por un tercero?»— surge desde cualquiera de las tres. Meterlo en la carpeta de una de ellas obligaría a las otras dos a importar de esa pantalla, que es justo la dependencia que la regla de abajo prohíbe |

**Tres reglas que no se ven mirando el árbol:**

- **Lo que entra y sale de una RUTA se toma de `paths`, nunca de `components`**
  (#133). `http.post<T>()` no comprueba nada, así que elegir `T` a mano deja el
  tipo sin atar a la ruta. Las piezas de dentro —las que se pasan a un
  componente— sí vienen de `components`, porque son formas con nombre propio.
- **Se comprueba, no se castea.** Todo lo que llega sin tipo —el `data` de una
  señal, el `payload` del historial, el `input_schema` de una herramienta— pasa
  por un guardián que devuelve `null` si no encaja, y lo que no encaja **se
  enseña en crudo** en vez de omitirse.
- **El estado va en `signal()`.** El proyecto es *zoneless*: guardarlo en un
  campo normal no da error, simplemente no repinta.

### La dirección de las dependencias

Una pantalla puede depender de `api/`; **ninguna debería depender de otra
pantalla**. Es lo que decidió, en #129, dónde vive `comoAnalisis`: el guardián
que lee un análisis del `payload` guardado nació en `historial/`, y desde allí
obligaba a `senal-card` —que sólo dibuja— a importar tipos de la pantalla del
historial para existir. Vive en `analisis/formas.ts`, junto a quien los pinta.

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

### 5 · `vocabulario.ts` sirve a tres pantallas desde `analisis/`

`nombreDeVeredicto` lo usa el historial y `nombreDeDimension` la de Sistema, así
que **dos pantallas importan de una tercera** — justo lo que el criterio de
arriba dice que no debería pasar. Son las traducciones del dominio a castellano,
y no pertenecen a la pantalla de análisis más que a las otras.

No se mueve todavía porque el destino natural —una carpeta compartida— tendría
hoy **un solo fichero dentro**, y una carpeta de un elemento suele ser una
decisión tomada antes de tiempo. El momento de moverlo es cuando aparezca el
segundo, y ya se sabe cuál: el chat de R13 va a querer los mismos nombres.

*(Comprobado el 2026-09-23: la importan `historial-page.ts` y `sistema-page.ts`.
H5 es lo siguiente, así que ese momento llega al abrir el chat, no antes.)*

---

## Bugs detectados

Al leer los módulos para escribir las descripciones de arriba salieron dos cosas
que sí hay que arreglar. **No son de la misma clase**, y conviene no meterlas en
el mismo saco.

### 1 · `linear.py` lee el fichero de pesos al importar — ✅ CERRADO (#108)

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

**Cerrado en #108** (2026-09-24). Los pesos se leen con `pesos()`, una función
cacheada, la primera vez que se usan. Un test recarga el módulo con `open`
saboteado y falla si alguien vuelve a leerlos al importar; se comprobó que el
código de antes lo habría hecho fallar. Había un consumidor de fuera que no
salía en la descripción del bug: `evaluation/eval_featurizado.py` leía
`linear.JSON`, y pasó a `linear.pesos()`.

### 2 · Dos señales de **forma** comparten extracción de rasgos — ✅ MEDIDO (#109)

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

No era un arreglo de código, sino **medirlo y añadir la consecuencia a la
ficha** — y se hizo en **#109**, con `eval_acoplamiento.py` y
`eval_featurizado.py`. Salió peor que una correlación: el acoplamiento es **por
construcción**, porque el veredicto del léxico es una función determinista del
vector que usa el lineal. En Chakraborty dev dan kappa 0,880, pero en el 50 % de
los titulares el vector sale vacío y las dos responden «no» sin mirar; donde
tiene contenido, el acuerdo baja al 88,0 %, y al 59,1 % en Webis-17. **La ficha
del lineal lo publica así**, y viaja al frontend por `describe_models`.

## Renombrados

Criterio: **renombrar cuando el nombre hace una predicción falsa**, no cuando es
escueto. `base.py` es escueto y predice bien; `linear_model.py` predecía «aquí
vive el modelo lineal» y era mentira.

| Fichero | Ahora | Por qué | Estado |
|---|---|---|---|
| `evaluation/linear_model.py` | `train_linear.py` | No contiene el modelo: lo **entrena**. El modelo vive en `nlp/linear.py` + el JSON. Y colisionaba de un vistazo con `nlp/linear.py`, que sí es la señal. Encaja además con sus hermanos, ya verbo+objeto: `eval_lexical`, `eval_external` | ✅ hecho en #108 |
| `nlp/client.py` | `remote.py` | El par `client.py` / `local.py` no decía que fueran **dos implementaciones de la misma interfaz**; `remote.py` / `local.py` sí. Y en las demás integraciones `client.py` significa otra cosa —«el cliente de esta API»—, así que además era inconsistente entre paquetes | ✅ hecho en #108 |
| `integrations/metadata.py` | *(se queda)* | Se propuso `tool_metadata.py`, pero su nombre es vago, no falso, y el criterio de arriba es la predicción falsa. El docstring ya lo cubre | descartado en #108 |

No se renombran `base.py`, `models.py`, `outputs.py` ni `nlp/linear.py`: son
escuetos pero no engañan, y con `train_linear.py` desaparece la única colisión
real.

**Un renombrado arrastra lo que nombre el fichero por su nombre**, y no sólo los
imports. El que no avisa es `tests/test_arquitectura.py`, que exceptúa de la
invariante de configuración a `remote.py` **por nombre de fichero**: si el
renombrado no la trae consigo, el test falla, porque `remote.py` lee `settings`.

## Deuda de docstrings — ✅ saldada (#108)

De los **40 módulos de `backend/`** —sin contar `evaluation/` ni los
`__init__.py`—, **todos declaran qué hacen desde #108**. Eran 16 sin docstring
el 2026-09-23, y 19 de 30 al escribir esta sección, concentrados en el código de
la Fase A. Se cuenta con `ast.get_docstring` sobre cada uno; el comando está en
la sección de #173 del README.

Cada docstring dice para qué existe el módulo y **lo que no se deduce
leyéndolo**, con la issue de la que sale. Las descripciones de las tablas de
arriba se sacaron leyendo definiciones, no docstrings, y **lo correcto es lo
contrario**: que cada módulo declare su propósito y este documento se limite a
los criterios y las relaciones, porque una línea en un fichero central es lo
primero que se queda obsoleto y un docstring está donde se edita el código.
Ahora que existen, las tablas podrían adelgazar; no se ha hecho todavía.
