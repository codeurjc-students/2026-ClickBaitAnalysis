#!/usr/bin/env bash
# #260 · Frente 1 del análisis de vulnerabilidades: las dependencias.
#
# Compara las versiones que usa el proyecto con los avisos publicados (CVE,
# GHSA, PYSEC). No dice si el código llama a lo vulnerable: eso es el triaje,
# aviso a aviso. Cinco pasadas, cada una en su JSON, en
# spikes/vulnerabilidades/<fecha>/:
#
#   pip_lockfile.json             requirements.txt, tal cual
#   pip_fuera_del_lockfile.json   torch y sentence-transformers, que el
#                                 Dockerfile instala fuera del lockfile
#   pip_imagen.json               el `pip freeze --all` de la imagen del
#                                 backend: lo que pip resolvió al construirla,
#                                 también lo que arrastran torch y
#                                 sentence-transformers, y lo que trae la
#                                 imagen base (pip, setuptools)
#   npm_todo.json                 `npm audit`, con las herramientas de compilación
#   npm_servido.json              `npm audit --omit=dev`: lo que llega a la web
#
# pip-audit consulta OSV (`-s osv`) y no el servicio de PyPI, que es el que usa
# por defecto: OSV junta los avisos de PyPA y los de GitHub, y de ahí sale
# también la gravedad, que pip-audit no da. Con `--no-deps --disable-pip` no
# instala nada: lee nombres y versiones, que el lockfile ya fija con `==`.
#
# Un aviso no es un error: pip-audit y npm audit salen con 1 cuando encuentran
# alguno, y el guion sigue. Lo que sí lo para es que falte un JSON.
#
# La imagen se mide por CONTENIDO, no por fecha: una reconstrucción que sale
# entera de caché no cambia la fecha de la imagen (pasó al empezar #260). Se
# exige que su requirements.txt sea el del repositorio y que su torch sea el
# del Dockerfile; si no, hay que reconstruir:
#   docker compose -f compose.yaml -f compose.local.yaml build
#
# Uso, desde la raíz y con Docker sin otra carga (#259):
#   bash spikes/vulnerabilidades_dependencias.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PIP_AUDIT_VERSION=2.10.1
VENV=/tmp/venv-auditoria
NODE_BIN=/home/ggarciac/.nvm/versions/node/v22.23.2/bin
IMAGEN=clickbait-backend
DOCKERFILE=docker/backend.Dockerfile
SALIDA="spikes/vulnerabilidades/$(date +%F)"
TEMPORAL="$(mktemp -d)"
trap 'rm -rf "$TEMPORAL"' EXIT

mkdir -p "$SALIDA"

# ── La herramienta, en su propio venv y con la versión fija ────────────────
if [ "$("$VENV/bin/pip-audit" --version 2>/dev/null)" != "pip-audit $PIP_AUDIT_VERSION" ]; then
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet "pip-audit==$PIP_AUDIT_VERSION"
fi
PIP_AUDIT=("$VENV/bin/pip-audit" --no-deps --disable-pip -s osv -f json --progress-spinner off)

# ── La imagen tiene que ser la del repositorio ─────────────────────────────
# Con `--all`: sin él, `pip freeze` no se lista a sí misma, y la pip de la
# imagen quedaba sin auditar (pasó en la primera pasada de #260).
docker run --rm --network none --entrypoint pip "$IMAGEN" freeze --all > "$SALIDA/imagen_freeze.txt"

hash_repositorio="$(sha256sum < requirements.txt | cut -d' ' -f1)"
hash_imagen="$(docker run --rm --network none --entrypoint cat "$IMAGEN" /app/requirements.txt | sha256sum | cut -d' ' -f1)"
if [ "$hash_repositorio" != "$hash_imagen" ]; then
    echo "La imagen $IMAGEN no tiene el requirements.txt del repositorio: reconstruirla." >&2
    exit 1
fi

# Las dos líneas de fuera del lockfile, sacadas del Dockerfile para que no se
# desfasen de lo que de verdad se instala.
grep -oE '(torch|sentence-transformers)==[0-9][0-9.]*' "$DOCKERFILE" > "$TEMPORAL/fuera_del_lockfile.txt"
torch_dockerfile="$(grep '^torch==' "$TEMPORAL/fuera_del_lockfile.txt")"
torch_imagen="$(grep -i '^torch==' "$SALIDA/imagen_freeze.txt")"
if [ "${torch_imagen%%+*}" != "$torch_dockerfile" ]; then
    echo "La imagen tiene $torch_imagen y el Dockerfile pide $torch_dockerfile: reconstruirla." >&2
    exit 1
fi

# ── Las condiciones ────────────────────────────────────────────────────────
{
    echo "fecha: $(date -Is)"
    echo "commit: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
    git diff --quiet HEAD -- requirements.txt "$DOCKERFILE" frontend/package-lock.json \
        || echo "  ⚠️ con cambios sin commitear en requirements.txt, el Dockerfile o el lockfile de npm"
    echo "$("$VENV/bin/pip-audit" --version), servicio de avisos: osv"
    echo "node: $("$NODE_BIN/node" --version), npm: $(PATH="$NODE_BIN:$PATH" npm --version)"
    echo "imagen: $IMAGEN $(docker image inspect -f '{{.Id}} creada {{.Created}}' "$IMAGEN")"
    echo "fuera del lockfile (de $DOCKERFILE): $(paste -sd' ' "$TEMPORAL/fuera_del_lockfile.txt")"
    echo "en el freeze de la imagen: $torch_imagen (se audita sin el sufijo local)"
} | tee "$SALIDA/condiciones.txt"

# ── Python ─────────────────────────────────────────────────────────────────
# El freeze, sin el sufijo local (`+cpu`), que la base de avisos no conoce, y
# sólo con las líneas fijadas con `==`: las demás se apuntan aparte.
grep -v '==' "$SALIDA/imagen_freeze.txt" > "$SALIDA/imagen_sin_auditar.txt" || true
grep '==' "$SALIDA/imagen_freeze.txt" | sed 's/+[A-Za-z0-9.]*$//' > "$TEMPORAL/imagen.txt"

"${PIP_AUDIT[@]}" -r requirements.txt -o "$SALIDA/pip_lockfile.json" || true
"${PIP_AUDIT[@]}" -r "$TEMPORAL/fuera_del_lockfile.txt" -o "$SALIDA/pip_fuera_del_lockfile.json" || true
"${PIP_AUDIT[@]}" -r "$TEMPORAL/imagen.txt" -o "$SALIDA/pip_imagen.json" || true

# ── npm ────────────────────────────────────────────────────────────────────
(
    cd frontend
    export PATH="$NODE_BIN:$PATH"
    npm audit --json > "../$SALIDA/npm_todo.json" || true
    npm audit --json --omit=dev > "../$SALIDA/npm_servido.json" || true
)

# ── Que no falte ninguna pasada ────────────────────────────────────────────
for pasada in pip_lockfile pip_fuera_del_lockfile pip_imagen npm_todo npm_servido; do
    if ! python3 -c 'import json, sys; json.load(open(sys.argv[1]))' "$SALIDA/$pasada.json" 2>/dev/null; then
        echo "Falta $SALIDA/$pasada.json, o no es JSON: la pasada falló." >&2
        exit 1
    fi
done

echo
echo "Hecho, en $SALIDA. El triaje: .venv/bin/python spikes/vulnerabilidades_resumen.py $SALIDA"
