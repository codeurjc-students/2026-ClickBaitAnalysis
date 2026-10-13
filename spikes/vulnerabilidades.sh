#!/usr/bin/env bash
# #260 · Comprobar las vulnerabilidades: los frentes que corren en esta máquina,
# de una vez y en orden. El procedimiento entero —qué hace falta, cuándo, cómo
# se tría y cómo se arregla— está en `docs/desarrollo.md`, §9.
#
#   1. dependencias   vulnerabilidades_dependencias.sh (pip-audit y npm audit)
#   2. su resumen     vulnerabilidades_resumen.py, con `--anterior` si se da
#   3. imágenes       vulnerabilidades_imagenes.sh (Trivy)
#   4. código         vulnerabilidades_codigo.sh (las reglas S de ruff)
#   5. secretos       vulnerabilidades_secretos.sh (gitleaks)
#
# Todos escriben en la MISMA carpeta, `spikes/vulnerabilidades/<fecha>-<etiqueta>/`:
# una carpeta es una comprobación entera. Falta CodeQL, que corre en GitHub; al
# terminar, el guion dice cómo lanzarlo.
#
# Antes, las imágenes construidas con lo que hay en la copia de trabajo
# (`docker compose -f compose.yaml -f compose.local.yaml build`): si no lo
# están, el paso 1 se niega y aquí se para todo. Cada paso se para con
# cualquier fallo; los avisos no son fallos.
#
# Uso, desde la raíz y con Docker sin otra carga (#259):
#   bash spikes/vulnerabilidades.sh <etiqueta> [--anterior <carpeta de otra comprobación>]
set -euo pipefail
cd "$(dirname "$0")/.."

ETIQUETA="${1:?Uso: bash spikes/vulnerabilidades.sh <etiqueta> [--anterior <carpeta>]}"
shift
ANTERIOR=()
if [ "${1:-}" = "--anterior" ]; then
    [ -d "${2:-}" ] || { echo "No existe la carpeta anterior «${2:-}»." >&2; exit 1; }
    ANTERIOR=(--anterior "$2")
fi
CARPETA="spikes/vulnerabilidades/$(date +%F)-$ETIQUETA"
inicio=$(date +%s)
paso() { echo; echo "=== $(( $(date +%s) - inicio )) s · $*"; }

paso "1/5 · dependencias"
bash spikes/vulnerabilidades_dependencias.sh "$ETIQUETA"
paso "2/5 · el resumen para el triaje"
python3 spikes/vulnerabilidades_resumen.py "$CARPETA" "${ANTERIOR[@]}"
paso "3/5 · imágenes"
bash spikes/vulnerabilidades_imagenes.sh "$ETIQUETA"
paso "4/5 · código"
bash spikes/vulnerabilidades_codigo.sh "$ETIQUETA"
paso "5/5 · secretos"
bash spikes/vulnerabilidades_secretos.sh "$ETIQUETA"

paso "hecho, en $CARPETA"
rama="$(git rev-parse --abbrev-ref HEAD)"
cat <<FIN
Falta CodeQL, que corre en GitHub (codeql.yml tiene que estar en dev, la rama
por defecto, para poder lanzarlo; analiza la rama que se le diga):

    gh workflow run codeql.yml --ref $rama
    gh run watch "\$(gh run list --workflow codeql.yml --branch $rama --limit 1 --json databaseId --jq '.[0].databaseId')"
    bash spikes/vulnerabilidades_codeql.sh $ETIQUETA

Y después, el triaje: docs/desarrollo.md, §9.
FIN
