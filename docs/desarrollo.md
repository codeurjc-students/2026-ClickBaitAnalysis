# Guía de desarrollo

Cómo se prepara un entorno para editar el código, ejecutarlo mientras se edita
y pasar las mismas comprobaciones que el CI. Para levantar la aplicación entera
con Docker, sin tocar el código, está [`ejecucion.md`](ejecucion.md).

Para orientarse en el código:

- [`estructura.md`](estructura.md): dónde vive cada cosa y con qué criterio.
- [`arquitectura.md`](arquitectura.md): cómo está montado, con sus diagramas.
- [`requisitos.md`](requisitos.md): lo que el sistema tiene que cumplir.
- Las [convenciones de ramas, commits y versiones](../README.md#convenciones-de-desarrollo),
  en el README.

## Lo que hace falta

- **git**.
- **Python 3.12**, con su módulo `venv`. En Ubuntu viene aparte, en el paquete
  `python3.12-venv`.
- **Node 22**, la versión que pide el CI; la imagen de la web fija la 22.23.2.
  Con [nvm](https://github.com/nvm-sh/nvm), `nvm install 22`.

Se ha desarrollado y comprobado en Ubuntu 24.04 dentro de WSL. Los comandos son
de bash y se ejecutan desde la raíz del repositorio, salvo los que empiezan con
`cd frontend`.

## 1 · El código

```bash
git clone https://github.com/codeurjc-students/2026-ClickBaitAnalysis.git
cd 2026-ClickBaitAnalysis
```

## 2 · El backend

Un entorno virtual en `.venv`, que es donde lo buscan `pyrightconfig.json` y
los comandos de esta guía, con las dependencias de ejecución:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

`requirements.txt` es un *lockfile*: lo genera `pip-compile` a partir de
`requirements.in`, con cada versión fijada, y no se edita a mano (ver
[«Cambiar una dependencia»](#8--cambiar-una-dependencia)).

Y las dos herramientas que corre el CI, en las versiones que corre:

```bash
.venv/bin/python -m pip install ruff==0.16.1 pyright==1.1.411
```

Con esto ya pasan las comprobaciones del backend que hace el CI (paso 6): las
pruebas no cargan ningún modelo ni salen a la red.

### Las señales NLP en local (opcional)

Con `requirements.txt` funcionan el léxico y el lineal, que son Python puro. La
dedicada, el tono y la incoherencia cargan un modelo con `torch`, que no está en
el lockfile porque pesa varios GB y depende del hardware; sin él, esas señales
responden diciendo qué paquete falta. Para tenerlas, primero `torch` en su
versión de CPU —si no, pip trae la de CUDA, mucho más grande— y después lo
demás:

```bash
.venv/bin/python -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements-dev.txt
```

La versión de `torch` es la de la imagen (`docker/backend.Dockerfile`).
`requirements-dev.txt` trae además `numpy` y `scikit-learn`, que usan los
guiones de `backend/evaluation/` para entrenar y medir. La primera vez que una
señal carga su modelo, lo descarga del Hub de Hugging Face a
`~/.cache/huggingface`.

## 3 · El frontend

```bash
cd frontend && npm ci
```

`npm ci` y no `npm install`: instala exactamente lo de `package-lock.json`, y
falla si no coincide con `package.json`. Es lo que hacen el CI y la imagen.

## 4 · La configuración

```bash
cp .env.example .env
```

**Es opcional**, y para desarrollar no hace falta rellenar ninguna clave:
analizar un titular no usa ninguna, las pruebas no salen a la red, y sin `.env`
todo arranca igual. Sin una clave sólo falla la herramienta de noticias de esa
API, que dice qué falta. Qué es cada variable, en
[`ejecucion.md`](ejecucion.md#la-configuración).

## 5 · Arrancar en desarrollo

Tres procesos, cada uno en su terminal:

| Proceso | Comando | Dónde |
|---|---|---|
| La API | `.venv/bin/uvicorn backend.api.app:app --reload` | `http://127.0.0.1:8000`, con la documentación en `/docs`. `--reload` la reinicia al guardar un fichero |
| El servidor MCP | `MCP_TRANSPORT=streamable-http .venv/bin/python -m backend.main` | `http://127.0.0.1:8765/mcp`, que es donde lo busca la API por defecto |
| La web | `cd frontend && npm start` | `http://localhost:4200`. Reenvía `/api` a la API del 8000 (`frontend/proxy.conf.json`), como hace Caddy en el despliegue |

Analizar un titular y el historial sólo necesitan la API. **El servidor MCP**
hace falta para la pantalla de Sistema —que lista y ejecuta las herramientas— y
para el asistente, que también las llama por MCP; sin él, Sistema lo enseña
como inalcanzable. Por defecto el servidor MCP habla por `stdio`, que es lo que
espera un cliente que lo lanza como subproceso, como Claude Desktop (más
abajo); la variable lo pone en HTTP.

**El asistente** necesita además un servidor [Ollama](https://ollama.com) con
un modelo. Se enciende con tres variables en el `.env`:

```bash
LLM_BACKEND=ollama
LLM_URL=http://127.0.0.1:11434
LLM_MODEL=<un modelo descargado en ese Ollama>
```

Sin `LLM_BACKEND`, la pestaña del asistente no aparece, y quien entre en
`/asistente` lee por qué. El modelo del despliegue y sus medidas están en
`backend/integrations/llm/model_card.py`; cómo se enciende en las máquinas de la
universidad, en [`despliegue/README.md`](../despliegue/README.md).

### Desde Claude Desktop, con esta copia

La guía de ejecución conecta Claude Desktop a la imagen de Docker
([`ejecucion.md`](ejecucion.md#desde-claude-desktop)). Para probar las
herramientas con el código que se está editando, Claude Desktop lanza el
servidor desde el `.venv` de esta copia:

```json
{
  "mcpServers": {
    "tfg-mcp-server": {
      "command": "wsl",
      "args": [
        "bash", "-c",
        "cd /ruta/al/repositorio && PREHEAT_MODELS=true .venv/bin/python -m backend.main"
      ]
    }
  }
}
```

Ésa es la de Windows con el repositorio en WSL. En macOS, `"command": "/bin/sh"`
y `"args": ["-c", "cd … && …"]`, con la misma línea.

- **El `cd` es lo que importa**: el `.env` se lee de la carpeta en la que
  arranca el proceso, y `backend` se importa desde ahí.
- **`PREHEAT_MODELS` va en la línea de comandos**, y no en el campo `env` de la
  configuración, porque ese campo no cruza a WSL.
- Claude Desktop sólo relee la configuración al abrirse, y se edita con ella
  cerrada ([`ejecucion.md`](ejecucion.md#desde-claude-desktop)). Y al cambiar
  el código, para que el servidor lo cargue, se vuelve a abrir.
- **Ejecuta lo que haya en la copia en ese momento**, también otra rama: al
  cambiar de rama, el servidor de Claude Desktop cambia con ella la siguiente
  vez que se abre. Para usarlo a diario, mejor la imagen.
- **Tarda más que la imagen** (medido en #267, con WSL en un PC de
  sobremesa). Con WSL en marcha, los modelos están listos entre 41 y 86 s
  después de abrir Claude Desktop. Con WSL recién arrancado —y una vez con WSL
  en marcha, sin causa conocida— el saludo tarda de 27 a 55 s y los modelos, de
  146 a 183 s: la primera pregunta espera a que terminen (de 47 a 93 s), y una
  que llegue antes del saludo la contesta Claude sin la herramienta, sin avisar
  ([`ejecucion.md`](ejecucion.md#desde-claude-desktop)).

Claude Code lo admite igual, con `claude mcp add tfg-mcp-server -- <comando>
<argumentos…>`. Esto no se ha comprobado.

## 6 · Lo que comprueba el CI

Lo mismo que corre `.github/workflows/ci.yml` en cada pull request y en cada
push a `dev` y a `main`. El backend:

```bash
.venv/bin/python -m pytest -m "not integration" --cov
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/pyright
```

Las pruebas marcadas `integration` llaman de verdad a las APIs externas: el CI
no las corre, y en local piden las claves en el `.env` (`pytest -m
integration`).

El frontend, en `frontend/`:

```bash
cd frontend
npm ci
npm run gen:api && git diff --exit-code src/app/api/schema.d.ts
npm run build
npm test -- --watch=false
npm run lint
```

La segunda línea comprueba que los tipos del cliente son los que salen del
contrato commiteado (paso 7). `npm test` corre Vitest sobre jsdom, sin
navegador; sin `--watch=false`, en una terminal se queda vigilando los ficheros.
`npm run lint` es ESLint, con las reglas de accesibilidad de las plantillas.

Por último, el CI construye las dos imágenes, sin publicarlas, sólo si todo lo
anterior pasa. En local, con Docker, las construye el compose:

```bash
docker compose build
```

## 7 · Cambiar el contrato de la API

La forma de lo que entra y sale de la API se declara una vez, en los modelos
Pydantic de `backend/api/schemas.py` y `backend/analysis/domain.py`, y el
frontend la deriva. Al cambiar uno:

```bash
.venv/bin/python -m backend.api.export_openapi
cd frontend && npm run gen:api
```

El primero escribe `frontend/openapi.json`, y el segundo genera de él
`frontend/src/app/api/schema.d.ts`. **Se commitean los dos**, para que la pull
request enseñe qué cambió del contrato. El CI vigila las dos mitades: una prueba
de Python exige que `openapi.json` sea el que sale de los modelos, y el job del
frontend, que `schema.d.ts` sea el que sale de `openapi.json`. Cómo se usan esos
tipos en el frontend, en [§8 de `arquitectura.md`](arquitectura.md#de-dónde-salen-sus-tipos).

## 8 · Cambiar una dependencia

**De Python**: se añade o se cambia en `requirements.in` y se regenera el
lockfile. `pip-tools` no está en ningún fichero de requisitos: es la herramienta
que los genera.

```bash
.venv/bin/python -m pip install pip-tools
.venv/bin/pip-compile requirements.in
.venv/bin/python -m pip install -r requirements.txt
```

Lo pesado y lo que sólo sirve para medir va a `requirements-dev.txt`, que el CI
no instala. Las herramientas del CI (`ruff`, `pyright`) van fijadas allí y en
`ci.yml`, y se cambian en los dos.

**Del frontend**: `npm install <paquete>` en `frontend/`, que actualiza
`package.json` y `package-lock.json`. Se commitean los dos, porque el CI y la
imagen instalan con `npm ci`, que falla si no coinciden.

## 9 · Comprobar las vulnerabilidades

Cómo se repite el análisis de vulnerabilidades de #260: qué se ejecuta, en qué
orden, dónde queda y cómo se tría. Por qué cada herramienta y lo que salió la
primera vez, en la sección de #260 del README.

**Cuándo**: antes de cada release, antes de la congelación del 15 de
diciembre, y cuando Dependabot abra una alerta (lo hace solo desde que el grafo
de dependencias está activado, el 13 de octubre de 2026). Ninguna de estas
pasadas va en el CI: un aviso publicado hoy pondría en rojo una pull request
que no ha cambiado nada.

### Lo que hace falta, una vez

Docker, `gh` autenticado, y dos binarios en `~/.local/bin`, **bajados de su
release y comprobados con su `checksums.txt`**. Nunca la imagen de Trivy de
Docker Hub ni su acción de GitHub: en marzo de 2026 se publicaron versiones
malignas de las dos (CVE-2026-33634). Los guiones exigen estas versiones:

```bash
mkdir -p ~/.local/bin && cd "$(mktemp -d)"
base=https://github.com/aquasecurity/trivy/releases/download/v0.75.0
curl -sSfLO $base/trivy_0.75.0_Linux-64bit.tar.gz
curl -sSfLO $base/trivy_0.75.0_checksums.txt
grep ' trivy_0.75.0_Linux-64bit.tar.gz$' trivy_0.75.0_checksums.txt | sha256sum -c -
tar -xzf trivy_0.75.0_Linux-64bit.tar.gz trivy && install -m 0755 trivy ~/.local/bin/

base=https://github.com/gitleaks/gitleaks/releases/download/v8.30.1
curl -sSfLO $base/gitleaks_8.30.1_linux_x64.tar.gz
curl -sSfLO $base/gitleaks_8.30.1_checksums.txt
grep ' gitleaks_8.30.1_linux_x64.tar.gz$' gitleaks_8.30.1_checksums.txt | sha256sum -c -
tar -xzf gitleaks_8.30.1_linux_x64.tar.gz gitleaks && install -m 0755 gitleaks ~/.local/bin/
```

`sha256sum -c` tiene que decir `OK`. `pip-audit` no hace falta instalarlo: lo
pone el guion, en su versión, en un entorno aparte (`/tmp/venv-auditoria`).

### Los pasos

Todos llevan **la misma etiqueta**, y todo cae en una carpeta,
`spikes/vulnerabilidades/<fecha>-<etiqueta>/`, que es la foto de ese momento.
Cada guion se niega a pisar sus propios ficheros.

```bash
docker compose -f compose.yaml -f compose.local.yaml build
bash spikes/vulnerabilidades.sh <etiqueta> --anterior spikes/vulnerabilidades/<la última>
```

El primero construye las imágenes con lo que hay en la copia de trabajo: si
no, los guiones se niegan a medir una imagen que no es la del repositorio (lo
comprueban por su contenido, no por su fecha). El segundo lanza en orden
dependencias, su resumen, imágenes, código y secretos, y se para en el primero
que falle. Docker, sin otra carga a la vez. Sin `--anterior`, el resumen no
marca lo nuevo.

Al terminar dice cómo lanzar **CodeQL**, que corre en GitHub y deja su informe
como artefacto, sin crear alertas. `workflow_dispatch` sólo se puede lanzar si
`codeql.yml` está en la rama por defecto (`dev`), y analiza la rama que se le
diga:

```bash
gh workflow run codeql.yml --ref <rama>
bash spikes/vulnerabilidades_codeql.sh <etiqueta>    # cuando la ejecución termine
```

### Lo que queda

| Ficheros | De | Qué es |
|---|---|---|
| `condiciones.txt`, `pip_*.json`, `npm_*.json`, `imagen_freeze.txt` | `vulnerabilidades_dependencias.sh` | pip-audit (con OSV) sobre el lockfile, las dos líneas de fuera (`torch`, `sentence-transformers`) y el `pip freeze --all` de la imagen; npm audit con y sin `--omit=dev` |
| `resumen.md`, `gravedades.json` | `vulnerabilidades_resumen.py` | **la tabla para triar**: cada aviso una vez, con su gravedad (la de GitHub), su arreglo, en qué pasadas sale y, con `--anterior`, si es nuevo |
| `trivy_*` | `vulnerabilidades_imagenes.sh` | los críticos y altos con arreglo de cada imagen, que se trían, y el recuento de todo lo demás |
| `ruff_s*` | `vulnerabilidades_codigo.sh` | las reglas S de ruff, separando lo que va en la imagen |
| `gitleaks*` | `vulnerabilidades_secretos.sh` | los secretos de todo el historial, sin el secreto |
| `codeql_*` | `vulnerabilidades_codeql.sh` | los dos SARIF de CodeQL y su resumen |

### Cómo se tría

Cada aviso **nuevo** acaba en una casilla: **arreglado**, **aceptado** (con su
motivo escrito) o **no aplicable**. Primero, si llega a lo servido: lo que va
en la imagen o en la web importa más que lo que sólo se usa para compilar o
probar (`tests/`, `spikes/`, `backend/evaluation/`, las dependencias de
desarrollo de npm). Un crítico o un alto que llegue a lo servido se arregla o
se justifica por escrito.

Lo ya aceptado, con su motivo, está en la sección de #260 del README: pip y lo
que lleva dentro (no hay versión que lo arregle), los avisos de Debian sin
arreglo publicado, los de Caddy pendientes de su siguiente versión, los dos
S608 de `api/history.py` y lo de `spikes/` en CodeQL. En gitleaks, lo ya
triado está en `.gitleaksignore` (por su huella) y en `.gitleaks.toml` (la
ruta de estos informes), y por eso una pasada limpia da 0.

### Cómo se arregla

**Python**: se sube cada paquete a lo mínimo que lo arregla, sin saltar de
versión principal, con un `-P` por paquete, y después se comprueba todo lo del
paso 6. Por ejemplo, `mcp` desde la versión que arregla su aviso y sin pasar a
la 2:

```bash
.venv/bin/pip-compile requirements.in -P "mcp>=1.28.1,<2"
.venv/bin/python -m pip install -r requirements.txt
```

Sin `-o`: con él, la cabecera del lockfile cambia. Si se suben `mcp` o
`fastmcp`, el catálogo que lee el agente se vuelca antes y después
(`spikes/catalogo_volcado.py`): si sale idéntico, no hace falta repetir el
examen del agente.

**npm**: `npm audit fix`, sin `--force`, y el paso 6. Si no mueve la familia
`@angular` —sus paquetes se exigen la misma versión entre sí, y npm no mueve
el grupo sobre el lockfile que ya tiene—, se quitan sus entradas del lockfile y
se resuelven de nuevo, dentro de los rangos de `package.json`:

```bash
cd frontend
python3 -c "import json; ruta = 'package-lock.json'; bloqueo = json.load(open(ruta)); [bloqueo['packages'].pop(clave) for clave in list(bloqueo['packages']) if 'node_modules/@angular/' in clave]; open(ruta, 'w').write(json.dumps(bloqueo, indent=2) + '\n')"
rm -rf node_modules && npm install && npm audit fix
```

**La imagen base** (`pip` y `setuptools`, fijados en el paso 0 de
`docker/backend.Dockerfile`) y **Caddy** (la etiqueta de `docker/web.Dockerfile`)
se suben en su Dockerfile.

Después de cualquier cambio en lo servido, la pila entera en local y la prueba
en vivo, que ejecuta cada herramienta con sus modelos cargados:

```bash
docker compose -f compose.yaml -f compose.local.yaml up --build --wait
.venv/bin/python spikes/produccion_en_vivo.py --local
docker compose -f compose.yaml -f compose.local.yaml down
```

**Un secreto** que gitleaks encuentre **se rota**: borrarlo del código no lo
quita del historial, que es público. Si es un falso positivo, su huella va a
`.gitleaksignore` con un comentario que diga por qué.
