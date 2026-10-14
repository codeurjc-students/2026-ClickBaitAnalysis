# Ejecución

Cómo se levanta el sistema entero con Docker, desde cero, en cualquier máquina.
Para editar el código está [`desarrollo.md`](desarrollo.md); para operar las
máquinas de la universidad —desplegar, encender el asistente y apagarlo—,
[`despliegue/README.md`](../despliegue/README.md).

## Qué se levanta

Tres contenedores, descritos en `compose.yaml`:

| Servicio | Qué es | Se llega desde |
|---|---|---|
| `web` | Caddy, con la web de Angular ya compilada. Es la única puerta: sirve la web y reenvía `/api` a la API | el navegador, por HTTPS |
| `api` | La API REST (FastAPI), que analiza los titulares, guarda el historial y lleva dentro el asistente | sólo `web` |
| `mcp` | El servidor MCP con las herramientas, de donde salen el catálogo y lo que ejecuta el asistente | sólo `api` |

Los modelos de las señales van **dentro de la imagen**, horneados al
construirla: el sistema analiza sin salir a internet. El historial vive en un
volumen, así que sobrevive a recrear los contenedores. El dibujo, en
[§10 de `arquitectura.md`](arquitectura.md#10--despliegue).

## Lo que hace falta

- **Docker Engine con Compose 2.24 o posterior**, por la variante local (más
  abajo). Comprobado con Docker 29.1.3 y Compose 2.40.3.
- **Red para construir**: descarga los paquetes de Python, `torch`, los cinco
  modelos del Hub de Hugging Face y los paquetes de npm.
- **Unos 6 GB de disco** para las dos imágenes —la del backend lleva `torch` y
  los modelos—, y unos 7 GB más de caché de construcción.
- **Unos 2 GB de memoria** con el sistema en marcha, casi todos de la API, que
  carga los modelos al arrancar. El servidor MCP carga los suyos la primera vez
  que se ejecuta una señal desde la pantalla de Sistema: hasta 1,2 GB más.
- **Los puertos 80 y 443** libres.

## La configuración

**Es opcional.** Analizar un titular no usa ninguna clave, y sin `.env` el
sistema arranca igual. Las claves sólo hacen falta para las herramientas de
noticias de cada API, y se ponen en un `.env` en la raíz:

```bash
cp .env.example .env
```

`.env.example` las trae todas, vacías. Sin una, o vacía, el registro lo avisa
al arrancar (`configuracion.claves_sin_configurar`, con los nombres de las que
faltan) y sólo falla la herramienta de esa API, que dice qué falta.

| Variable | Para qué | Dónde se saca | Sin ella |
|---|---|---|---|
| `GUARDIAN_API_KEY` | Las noticias de The Guardian (`get_guardian_news`) y su sonda de salud | open-platform.theguardian.com | Su herramienta dice que falta, y la salud la da por «no configurada» |
| `NYT_API_KEY` | Las de The New York Times (`get_nyt_news`) y su sonda. Admite 500 llamadas al día | developer.nytimes.com | Igual que la de Guardian |
| `HF_TOKEN` | Sólo la vía remota de los modelos (`NLP_BACKEND=remote`), de pago desde octubre de 2026 | huggingface.co/settings/tokens | Con la vía local, la del despliegue, no se usa |
| `GNEWS_API_KEY` | Noticias en español de GNews (`get_gnews_news`). Admite 100 peticiones al día | gnews.io | Su herramienta dice que falta |
| `NEWSDATA_API_KEY` | Noticias en español de NewsData.io (`get_newsdata_news`) | newsdata.io | Igual |

### Los demás ajustes

Todos tienen un valor por defecto, y se cambian añadiendo la variable al `.env`.
Las listas y los diccionarios se escriben en JSON. **Lo que fija el compose, en
su `environment`, manda sobre el `.env`**: es lo que define el despliegue, y va
a la vista en el repositorio. El porqué de cada valor está junto a su campo, en
`backend/config/settings.py`. Estas tablas las vigila
`tests/test_documentacion.py`: un ajuste nuevo sin su fila, o la fila de uno que
ya no existe, hace fallar el CI.

**Registro**

| Variable | Por defecto | En el compose | Qué decide |
|---|---|---|---|
| `LOG_LEVEL` | `INFO` | — | `DEBUG`, `INFO`, `WARNING` o `ERROR` |
| `LOG_FORMAT` | `console` | — | `console` para leerlo, `json` para procesarlo |

**Las señales**

| Variable | Por defecto | En el compose | Qué decide |
|---|---|---|---|
| `NLP_BACKEND` | `local` | `local`, en `api` y `mcp` | Dónde corren los modelos: en el proceso, o en la Inference API de Hugging Face (`remote`, de pago, con `HF_TOKEN`) |
| `NLP_MODELS` | `{}` | — | Otro modelo para una señal: `{"detect_clickbait": "org/modelo"}`. Es un experimento: la ficha deja de publicar sus medidas. En la imagen no hay red, así que un modelo que no se horneó no se descarga |
| `NLP_MODELS_ES` | `{}` | — | Lo mismo, para los titulares en español |
| `NLP_THRESHOLDS` | `{}` | — | Otro umbral para el léxico o la incoherencia: `{"detect_clickbait_lexical": 2}` |
| `NLP_THRESHOLDS_ES` | `{}` | — | El de la incoherencia en español |
| `NLP_LINEAR_TOP_CUES` | el del lineal | — | Cuántas pistas enseña el lineal como explicación |
| `PREHEAT_MODELS` | `false` | `true`, en `api` | Cargar los modelos al arrancar, en vez de en la primera petición: la API, antes de servir; el servidor MCP, mientras ya atiende |

**El servidor MCP y el catálogo**

| Variable | Por defecto | En el compose | Qué decide |
|---|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `streamable-http`, en `mcp` | Cómo habla el servidor: `stdio` para un cliente que lo lanza, HTTP para la red |
| `MCP_HOST` | `127.0.0.1` | `0.0.0.0`, en `mcp` | Dónde escucha, con HTTP |
| `MCP_PORT` | `8765` | — | En qué puerto |
| `MCP_SERVERS` | `["http://127.0.0.1:8765/mcp"]` | `["http://mcp:8765/mcp"]`, en `api` | De qué servidores saca la API el catálogo |
| `MCP_TIMEOUT` | `5.0` | — | Segundos para dar un servidor por inalcanzable |
| `MCP_EXECUTE_TIMEOUT` | `60.0` | — | Segundos para ejecutar una herramienta; al agotarse, 504 |

**La API**

| Variable | Por defecto | En el compose | Qué decide |
|---|---|---|---|
| `CORS_ORIGINS` | `["http://localhost:4200"]` | el dominio; en la variante local, `["https://localhost"]` | Los orígenes que admite CORS |
| `HISTORY_DB` | `var/history.db` | — | El fichero del historial; en la imagen, dentro del volumen |
| `HISTORY_MAX_ENTRIES` | `1000` | — | Cuántas entradas guarda; `0`, sin límite |
| `HISTORY_MAX_DAYS` | `30` | — | Cuántos días; `0`, sin límite |
| `RATE_LIMIT_ENABLED` | `true` | — | El límite de peticiones por cliente |
| `RATE_LIMIT_WINDOW_S` | `60.0` | — | La ventana del límite, en segundos |
| `RATE_LIMIT_ANALYZE` | `10` | — | Por ventana, para analizar, ejecutar una herramienta y el chat |
| `RATE_LIMIT_HEALTH` | `20` | — | Para la salud |
| `RATE_LIMIT_DEFAULT` | `60` | — | Para el resto |
| `HEALTH_CACHE_S` | `30.0` | — | Cuánto vale un sondeo de salud antes de repetirlo; `0`, sin caché |

**El asistente**

| Variable | Por defecto | En el compose | Qué decide |
|---|---|---|---|
| `LLM_BACKEND` | ninguno: sin asistente | `ollama`, en `api` | Si hay asistente, y con qué servidor de modelos |
| `LLM_URL` | `http://127.0.0.1:11434` | `http://host.docker.internal:11434`, en `api` | Dónde está ese servidor |
| `LLM_MODEL` | `qwen3.5:27b` | — | El modelo |
| `LLM_NUM_CTX` | `16384` | — | Su ventana de contexto, en tokens |
| `LLM_NUM_PREDICT` | `1500` | — | Tope de salida por vuelta |
| `LLM_TEMPERATURE` | `0.6` | — | Muestreo |
| `LLM_PRESENCE_PENALTY` | `0.0` | — | Muestreo |
| `LLM_KEEP_ALIVE` | `10m` | — | Cuánto sigue el modelo en memoria tras la última petición |
| `LLM_TIMEOUT` | `300.0` | — | Segundos por llamada al modelo |
| `LLM_PROMPT` | `05-llano` | — | El prompt de sistema, de los de `backend/agent/prompts/` |
| `CHAT_QUEUE_SIZE` | `2` | — | Conversaciones en espera; con la cola llena, 503 |
| `CHAT_JOB_TTL_S` | `900.0` | — | Cuánto se guarda una conversación terminada |
| `CHAT_MAX_JOBS` | `20` | — | Cuántas como mucho |
| `CHAT_MAX_HISTORY_CHARS` | `4000` | — | Tope del historial que manda la web; por encima, 422 |

## Arrancar

`compose.yaml` es el despliegue de la máquina de la universidad, con su nombre
y su certificado. En cualquier otra se le suma **`compose.local.yaml`**, que
cambia sólo eso: sirve `localhost`, con un certificado que firma el propio
Caddy, y publica los puertos únicamente en el equipo.

```bash
git clone https://github.com/codeurjc-students/2026-ClickBaitAnalysis.git
cd 2026-ClickBaitAnalysis
docker compose -f compose.yaml -f compose.local.yaml up --build --wait
```

Con el `.env` de arriba, si se quieren las noticias; sin él, igual. Si el
usuario no está en el grupo `docker`, cada orden de `docker` va con `sudo`. `--wait` no vuelve hasta que los tres servicios están sanos. La primera
vez construye las dos imágenes: sin nada descargado, tardó unos 10 minutos con
una conexión doméstica. Después, con la caché, sólo se rehace lo que cambia.

**Se abre en `https://localhost`.** El navegador avisa del certificado, porque
lo firma una autoridad que sólo existe dentro del contenedor; se acepta el
aviso. Desde WSL, el navegador de Windows llega igual a `https://localhost`.

Para comprobarlo sin navegador (`-k` acepta ese certificado):

```bash
curl -sk https://localhost/api/health
curl -sk https://localhost/api/analyze -H 'Content-Type: application/json' \
  -d '{"headline": "You Will Never Believe What This Cat Did Next"}'
```

La salud sale `degraded` mientras falten las claves de Guardian y NYT, que da
por «no configuradas». El análisis devuelve el veredicto con sus cinco señales: la incoherencia queda en
`not_applicable`, porque compara el titular con el cuerpo, y sin `"content"` no
hay cuerpo.

## El asistente

Necesita un servidor [Ollama](https://ollama.com) con el modelo. El compose lo
busca en el equipo, en `http://host.docker.internal:11434`, y sin él la pantalla
del asistente explica que está apagado; todo lo demás funciona igual.

En las máquinas de la universidad el modelo corre en otra, con GPU, y llega por
un túnel que se abre bajo demanda: [`despliegue/README.md`](../despliegue/README.md).
En otra máquina, hace falta un Ollama que escuche donde lo alcanza el
contenedor —la puerta de enlace de Docker, `172.17.0.1`, y no el `127.0.0.1` del
equipo— y, en el `.env`, `LLM_MODEL` con un modelo que tenga descargado. Esto no
se ha comprobado fuera de las máquinas de la universidad.

## Desde Claude Desktop

Las herramientas del servidor MCP —las mismas que usa el asistente— se pueden
usar desde un cliente MCP de fuera del sistema, como Claude Desktop. El cliente
lanza el servidor como un subproceso y habla con él por la entrada y la salida
estándar (`stdio`), así que **no hace falta tener el compose arrancado**: basta
con la imagen `clickbait-backend` ya construida, que lleva los modelos dentro.
Cada vez que se abre Claude Desktop arranca un contenedor nuevo, y al cerrarla
se borra; no comparte nada con el de `compose.yaml`.

Se declara en `claude_desktop_config.json`, que vive en
`%APPDATA%\Claude\` en Windows y en `~/Library/Application Support/Claude/` en
macOS. En Windows, con Claude Desktop instalada como paquete (MSIX), ese
`%APPDATA%` es una carpeta virtual que sólo ve ella: desde fuera —un editor,
PowerShell— el fichero está en
`%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\`.
**Se edita con Claude Desktop cerrada**, también en la bandeja del sistema:
abierta, escribe encima la configuración que leyó al arrancar, y el cambio se
pierde sin avisar (las dos cosas, vistas en #267). Si ya existe, se añade la
entrada dentro de `mcpServers`:

```json
{
  "mcpServers": {
    "tfg-mcp-server": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--env-file", "/ruta/al/repositorio/.env",
        "-e", "PREHEAT_MODELS=true",
        "clickbait-backend", "python", "-m", "backend.main"
      ]
    }
  }
}
```

- **`-i` es obligatorio**: sin él, el contenedor no lee lo que le manda el
  cliente. Y sin `-t`, porque una terminal mezclaría su salida con la del
  protocolo.
- **`--env-file`** va con la ruta absoluta del `.env`, porque Claude Desktop no
  arranca en la carpeta del repositorio. Sólo hace falta para las noticias: sin
  `.env`, se quitan esas dos entradas, porque `docker` falla si el fichero no
  existe.
- **`PREHEAT_MODELS=true`** carga los modelos en cuanto arranca el servidor,
  mientras ya atiende al cliente (#267). Sin él, el primer análisis los carga
  dentro de la llamada, y puede tardar más de lo que el cliente espera. Con
  él, medido con Docker en WSL, los tiene listos unos 15 s después de abrir
  Claude Desktop, y en torno a un minuto y medio la primera vez que se lee la
  imagen desde que arrancó WSL. Una pregunta que llegue antes espera lo que
  falte.
- **En Windows, con Docker dentro de WSL**, el comando es `wsl` y `docker` pasa
  a ser el primer argumento: `"command": "wsl", "args": ["docker", "run", "-i",
  …]`. La ruta del `.env` es la de WSL (`/home/…/.env`).

Después se cierra Claude Desktop del todo —en Windows sigue abierta en la
bandeja del sistema— y se vuelve a abrir. Para comprobarlo, en una conversación
se le pide, por ejemplo, qué modelos usa el sistema: tiene que llamar a
`describe_models`. **Si contesta sin llamarla, el servidor aún no estaba
conectado**: mientras arranca, Claude no tiene sus herramientas y responde por
su cuenta, sin avisar. Pasó con la variante de `desarrollo.md` y WSL recién
arrancado: el saludo tardó 49 s, y un titular pedido antes lo analizó Claude
solo (#267). En el diálogo «Servidores MCP» de una sesión de Code aparece con
✓ cuando ya está conectado. Si el servidor no aparece, el motivo está en su
registro, `mcp-server-tfg-mcp-server.log`, en `%LOCALAPPDATA%\Claude\Logs\` en
Windows (hasta agosto de 2026, en `%APPDATA%\Claude\logs\`) y en
`~/Library/Logs/Claude/` en macOS.

Para usar el código de una copia del repositorio en vez de la imagen, al
editarlo, está la variante de [`desarrollo.md`](desarrollo.md#desde-claude-desktop-con-esta-copia).

**Lo que no se hace**: conectar Claude Desktop al servidor MCP del despliegue.
No tiene autenticación, y por eso el compose no publica su puerto: sólo lo
alcanza la API, dentro de su red.

## Parar

```bash
docker compose -f compose.yaml -f compose.local.yaml down
```

`down` conserva el historial, que vive en un volumen. **`down -v` lo borra**, y
con él la autoridad de Caddy: la siguiente vez firmará otra.

## En la máquina de la universidad

Allí se usa `compose.yaml` solo, sin la variante. Sirve
`gongarcia.tfg.etsii.urjc.es` con un certificado autofirmado que vive en la
máquina, en `/etc/clickbait/tls` (`certificado.pem` y `clave.pem`), y publica los
puertos 80 y 443 a internet. Cómo se despliega, se comprueba y se para, en
[`despliegue/README.md`](../despliegue/README.md).
