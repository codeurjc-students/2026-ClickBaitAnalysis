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
espera un cliente como Claude Desktop, que lo lanza como subproceso; la
variable lo pone en HTTP.

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
