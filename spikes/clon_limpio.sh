#!/bin/bash
# ¿Funcionan las dos guías al pie de la letra en un clon limpio? (#251)
#
#   bash spikes/clon_limpio.sh desarrollo   # docs/desarrollo.md
#   bash spikes/clon_limpio.sh ejecucion    # docs/ejecucion.md, con Docker
#
# Clona el repositorio de GitHub en /tmp/clon-limpio-<modo>, se pone en la rama
# `RAMA` (por defecto `dev`) y, salvo con `SIN_CAMBIOS=1`, copia encima lo que
# la copia de trabajo tenga sin commitear: así se prueba una rama antes de
# subirla, tal como quedará en `dev`. Después sigue la guía paso a paso, con sus
# comandos literales, y escribe cada resultado con su código de salida.
#
# `ejecucion` levanta el sistema con `compose.local.yaml`, mide lo que cita
# `ejecucion.md` —tiempo de construcción, tamaño de las imágenes y memoria de
# cada contenedor, leída de /proc/1/status porque `docker stats` no cuenta la
# respaldada por ficheros (#164)— y llama a todo por https://localhost, sin
# `.env`, que desde #259 es opcional. Al terminar hace `down`, salvo con
# `MANTENER=1`. Necesita los puertos 80 y 443 libres, y no toca las imágenes ni
# la caché de construcción: para medir en frío hay que vaciarlas antes, con
# `docker system prune -a` (sin `buildx`, como en el Docker de Ubuntu,
# `docker builder prune` no vacía la caché que usa el compose).
#
# Lo largo se lanza desacoplado y se lee el registro:
#
#   setsid nohup bash spikes/clon_limpio.sh ejecucion > /tmp/clon_ejecucion.log 2>&1 < /dev/null & disown
#
# Resultados del 12 oct 2026, en la sección de #251 del README.

set -u
MODO="${1:-}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CLON="/tmp/clon-limpio-$MODO"
inicio=$(date +%s)
paso() { echo; echo "=== $(( $(date +%s) - inicio )) s · $*"; }
resultado() { echo "--- código $1: $2"; }

case "$MODO" in desarrollo | ejecucion) ;; *) echo "uso: $0 desarrollo|ejecucion"; exit 2 ;; esac

# Un lector de la respuesta de /analyze, fuera de las comillas del guion.
LECTOR=$(mktemp --suffix=.py)
cat > "$LECTOR" <<'PY'
import json
import sys

respuesta = json.load(sys.stdin)
analisis = respuesta["analysis"]
veredicto = analisis["verdict"]
print(
    "  id", respuesta.get("id"), "· idioma", analisis.get("language"),
    "· veredicto", veredicto.get("label") if isinstance(veredicto, dict) else veredicto,
)
for senal in analisis["signals"]:
    detalle = (senal.get("detail") or "")[:80]
    print(f"    {senal['name']:30} {senal['status']:15} {detalle}")
PY

paso "el código: clon de GitHub, en ${RAMA:-dev}"
rm -rf "$CLON"
git clone -q https://github.com/codeurjc-students/2026-ClickBaitAnalysis.git "$CLON" < /dev/null
cd "$CLON" || { echo "FIN con fallo"; exit 1; }
git checkout -q "${RAMA:-dev}" && git log --oneline -1
if [ "${SIN_CAMBIOS:-0}" != 1 ]; then
  for fichero in $(git -C "$REPO" ls-files -m -o --exclude-standard); do
    mkdir -p "$(dirname "$fichero")" && cp "$REPO/$fichero" "$fichero" && echo "  copiado de la copia de trabajo: $fichero"
  done
fi

if [ "$MODO" = desarrollo ]; then
  export PATH="$HOME/.nvm/versions/node/v22.23.2/bin:$PATH"

  paso "2 · el backend"
  python3 -m venv .venv
  .venv/bin/python -m pip install -q -r requirements.txt; resultado $? "pip install -r requirements.txt"
  .venv/bin/python -m pip install -q ruff==0.16.1 pyright==1.1.411; resultado $? "ruff y pyright"

  paso "3 · el frontend"
  (cd frontend && npm ci > /tmp/clon_limpio_npm.txt 2>&1); resultado $? "npm ci"
  grep -E 'vulnerabilit' /tmp/clon_limpio_npm.txt

  paso "4 · la configuración"
  cp .env.example .env; resultado $? "cp .env.example .env"

  paso "5 · arrancar los tres procesos, y llamarlos por el proxy de ng serve"
  if ss -ltn | grep -qE ':(8000|8765|4200) '; then
    resultado 1 "los puertos 8000, 8765 o 4200 están ocupados"
  else
    # Cada proceso en su sesión, para pararlo entero: uvicorn --reload y ng
    # serve lanzan hijos. El pid guardado es el del líder de la sesión.
    lanzar() {
      local nombre="$1"; shift
      setsid bash -c 'echo $$ > "/tmp/clon_limpio_$0.pid"; exec "$@"' "$nombre" "$@" \
        > "/tmp/clon_limpio_$nombre.log" 2>&1 < /dev/null &
    }
    lanzar api .venv/bin/uvicorn backend.api.app:app --reload
    lanzar mcp env MCP_TRANSPORT=streamable-http .venv/bin/python -m backend.main
    (cd frontend && lanzar web npm start)
    for url in http://127.0.0.1:8000/openapi.json http://127.0.0.1:8765/mcp http://127.0.0.1:4200/; do
      hasta=$(( $(date +%s) + 180 ))
      until codigo=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url"); [ "$codigo" != 000 ] || [ "$(date +%s)" -ge "$hasta" ]; do sleep 2; done
      echo "  $url -> $codigo a los $(( $(date +%s) - inicio )) s"
    done
    echo "  GET / -> $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:4200/)"
    echo "  GET /api/health -> $(curl -s --max-time 30 http://127.0.0.1:4200/api/health | python3 -c 'import json, sys; salud = json.load(sys.stdin); print(salud["status"], {nombre: sonda["reachable"] for nombre, sonda in salud["integrations"].items()})')"
    echo "  POST /api/analyze:"
    curl -s --max-time 120 -X POST http://127.0.0.1:4200/api/analyze -H 'Content-Type: application/json' \
      -d '{"headline": "You Will Never Believe What This Cat Did Next"}' | python3 "$LECTOR"
    echo "  GET /api/tools -> $(curl -s --max-time 60 http://127.0.0.1:4200/api/tools | python3 -c 'import json, sys; catalogo = json.load(sys.stdin); print([(servidor["status"], servidor["tool_count"]) for servidor in catalogo["servers"]])')"
    echo "  GET /api/agent -> $(curl -s --max-time 10 http://127.0.0.1:4200/api/agent | python3 -c 'import json, sys; print(json.load(sys.stdin)["availability"]["status"])')"
    for nombre in web mcp api; do
      pid=$(cat "/tmp/clon_limpio_$nombre.pid" 2>/dev/null) && kill -- "-$pid" 2>/dev/null
    done
    sleep 3
    ss -ltn | grep -qE ':(8000|8765|4200) ' && resultado 1 "queda algo escuchando" || echo "  parados, y los puertos libres"
  fi

  paso "6 · el CI: backend"
  .venv/bin/python -m pytest -m "not integration" --cov -q -p no:cacheprovider > /tmp/clon_limpio_pytest.txt 2>&1; codigo=$?
  grep -E '^(TOTAL|[0-9]+ (passed|failed)|FAILED|ERROR)' /tmp/clon_limpio_pytest.txt | tail -8
  resultado $codigo "pytest"
  .venv/bin/python -m ruff check .; resultado $? "ruff check"
  .venv/bin/python -m ruff format --check .; resultado $? "ruff format --check"
  .venv/bin/pyright > /tmp/clon_limpio_pyright.txt 2>&1; codigo=$?
  grep -E 'errors?,' /tmp/clon_limpio_pyright.txt | tail -1; resultado $codigo "pyright"

  paso "6 · el CI: frontend"
  cd frontend || exit 1
  npm ci > /dev/null 2>&1; resultado $? "npm ci"
  npm run gen:api > /dev/null 2>&1 && git diff --exit-code src/app/api/schema.d.ts; resultado $? "gen:api y diff de schema.d.ts"
  npm run build > /tmp/clon_limpio_build.txt 2>&1; codigo=$?; grep -E 'complete|rror' /tmp/clon_limpio_build.txt | tail -2; resultado $codigo "npm run build"
  npm test -- --watch=false > /tmp/clon_limpio_vitest.txt 2>&1; codigo=$?
  sed 's/\x1b\[[0-9;]*m//g' /tmp/clon_limpio_vitest.txt | grep -E 'Test Files|Tests ' | tail -2; resultado $codigo "npm test -- --watch=false"
  npm run lint > /tmp/clon_limpio_lint.txt 2>&1; codigo=$?; tail -2 /tmp/clon_limpio_lint.txt; resultado $codigo "npm run lint"
  cd ..

  paso "7 · el contrato, regenerado: no tiene que cambiar nada"
  .venv/bin/python -m backend.api.export_openapi > /dev/null; resultado $? "export_openapi"
  (cd frontend && npm run gen:api > /dev/null 2>&1); resultado $? "gen:api"
  git diff --quiet -- frontend/openapi.json frontend/src/app/api/schema.d.ts; resultado $? "contrato sin cambios"

  paso "8 · pip-compile sin cambiar nada no tiene que mover el lockfile"
  .venv/bin/python -m pip install -q pip-tools; resultado $? "pip-tools"
  .venv/bin/pip-compile -q requirements.in 2> /dev/null; resultado $? "pip-compile"
  git diff --stat -- requirements.txt
  git diff --quiet -- requirements.txt; resultado $? "requirements.txt sin cambios"
fi

if [ "$MODO" = ejecucion ]; then
  COMPOSE=(docker compose -f compose.yaml -f compose.local.yaml)
  docker --version; docker compose version

  # Sin `.env`, a propósito: desde #259 es opcional, y el camino mínimo de la
  # guía es clonar y levantar. Las claves sólo hacen falta para las noticias.
  paso "la configuración: ninguna"
  if [ -e .env ]; then resultado 1 "hay un .env y no debería"; else echo "  sin .env"; fi

  paso "arrancar: construir en frío y esperar a los tres sanos"
  if ss -ltn | grep -qE ':(80|443) '; then resultado 1 "los puertos 80 o 443 están ocupados"; echo "FIN"; exit 1; fi
  free -m | sed -n '1,2p'
  t0=$(date +%s)
  "${COMPOSE[@]}" up --build --wait < /dev/null > /tmp/clon_limpio_compose.txt 2>&1; codigo=$?
  echo "  up --build --wait: $(( $(date +%s) - t0 )) s"
  tail -6 /tmp/clon_limpio_compose.txt
  resultado $codigo "docker compose up --build --wait"
  "${COMPOSE[@]}" ps --format '  {{.Service}}: {{.Status}}' < /dev/null

  paso "lo que ocupa"
  for imagen in clickbait-backend clickbait-web; do
    echo "  $imagen: $(docker image inspect "$imagen" --format '{{.Size}}' | awk '{printf "%.2f GB", $1/1e9}')"
  done
  docker image ls
  docker system df

  paso "la memoria de cada proceso (de /proc/1/status) y la del equipo"
  for servicio in api mcp web; do
    echo "  $servicio: $("${COMPOSE[@]}" exec -T "$servicio" sh -c 'grep -E "^(VmRSS|RssAnon|RssFile)" /proc/1/status' < /dev/null | tr -s ' \t' ' ' | tr '\n' ' ')"
  done
  free -m | sed -n '1,2p'

  paso "por https://localhost"
  echo "  GET / -> $(curl -sk -o /dev/null -w '%{http_code} %{content_type}' --max-time 10 https://localhost/)"
  echo "  GET http:// -> $(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 10 http://localhost/historial)"
  echo "  GET /api/health -> $(curl -sk --max-time 30 https://localhost/api/health | python3 -c 'import json, sys; salud = json.load(sys.stdin); print(salud["status"], {nombre: sonda["reachable"] for nombre, sonda in salud["integrations"].items()})')"
  echo "  POST /api/analyze, el ejemplo de la guía:"
  curl -sk --max-time 120 https://localhost/api/analyze -H 'Content-Type: application/json' \
    -d '{"headline": "You Will Never Believe What This Cat Did Next"}' | python3 "$LECTOR"
  echo "  POST /api/analyze, con cuerpo:"
  curl -sk --max-time 120 https://localhost/api/analyze -H 'Content-Type: application/json' \
    -d '{"headline": "You Will Never Believe What This Cat Did Next", "content": "A cat in Ohio learned to open the fridge and ate a whole roast chicken while its owners were asleep."}' | python3 "$LECTOR"
  echo "  POST /api/analyze, en español:"
  curl -sk --max-time 120 https://localhost/api/analyze -H 'Content-Type: application/json' \
    -d '{"headline": "No vas a creer lo que hizo este gato cuando nadie lo miraba"}' | python3 "$LECTOR"
  echo "  GET /api/tools -> $(curl -sk --max-time 60 https://localhost/api/tools | python3 -c 'import json, sys; catalogo = json.load(sys.stdin); print([(servidor["status"], servidor["tool_count"]) for servidor in catalogo["servers"]])')"
  echo "  GET /api/agent -> $(curl -sk --max-time 30 https://localhost/api/agent | python3 -c 'import json, sys; print(json.load(sys.stdin)["availability"]["status"])')"

  if [ "${MANTENER:-0}" != 1 ]; then
    paso "parar: down conserva el historial"
    "${COMPOSE[@]}" down < /dev/null > /dev/null 2>&1; resultado $? "docker compose down"
    docker volume ls --format '  {{.Name}}' | grep clickbait
  else
    paso "se queda en marcha (MANTENER=1)"
  fi
fi

rm -f "$LECTOR"
echo
echo "FIN en $(( $(date +%s) - inicio )) s"
