#!/usr/bin/env bash
# #260 · Frente 3 del análisis de vulnerabilidades: CodeQL, el resultado.
#
# CodeQL no corre aquí: lo lanza `.github/workflows/codeql.yml` en GitHub, que
# deja el informe (SARIF) como artefacto de la ejecución y no lo sube a code
# scanning. Este guion toma la ÚLTIMA ejecución de ese flujo en la rama actual,
# exige que haya terminado bien, descarga los dos SARIF (Python y
# JavaScript/TypeScript) a la carpeta de la comprobación y los resume:
#
#   codeql_<lenguaje>.sarif   el informe tal cual, para poder recontar
#   codeql_resumen.txt        cada hallazgo con su regla, su gravedad de
#                             seguridad, fichero y línea, y si está en lo que
#                             se sirve: `backend/` sin `evaluation/` (la
#                             imagen), `docker/` (al construirla) y
#                             `frontend/src/` sin las pruebas (la web)
#   codeql_condiciones.txt    la ejecución, su commit y la versión de CodeQL
#
# La gravedad es la `security-severity` que CodeQL da a cada regla (CVSS de 0 a
# 10): crítica desde 9, alta desde 7, media desde 4. Se niega si ya están sus
# ficheros, y avisa si la ejecución no es del commit que hay aquí.
#
# Uso, desde la raíz (con `gh` autenticado):
#   bash spikes/vulnerabilidades_codeql.sh [etiqueta]
set -euo pipefail
cd "$(dirname "$0")/.."

ETIQUETA="${1:-}"
SALIDA="spikes/vulnerabilidades/$(date +%F)${ETIQUETA:+-$ETIQUETA}"
RAMA="$(git rev-parse --abbrev-ref HEAD)"
TEMPORAL="$(mktemp -d)"
trap 'rm -rf "$TEMPORAL"' EXIT

if [ -e "$SALIDA/codeql_resumen.txt" ]; then
    echo "$SALIDA ya tiene una pasada de CodeQL: se pisaría. Dale otra etiqueta." >&2
    exit 1
fi

gh run list --workflow codeql.yml --branch "$RAMA" --limit 1 \
    --json databaseId,headSha,status,conclusion,createdAt,url > "$TEMPORAL/ejecucion.json"
read -r ejecucion commit estado conclusion fecha enlace < <(python3 -c '
import json, sys
datos = json.load(open(sys.argv[1]))
if not datos:
    print("- - - - - -")
else:
    ultima = datos[0]
    print(ultima["databaseId"], ultima["headSha"][:7], ultima["status"],
          ultima["conclusion"] or "-", ultima["createdAt"], ultima["url"])
' "$TEMPORAL/ejecucion.json")
if [ "$ejecucion" = "-" ]; then
    echo "No hay ninguna ejecución de codeql.yml en $RAMA." >&2
    exit 1
fi
if [ "$estado" != "completed" ] || [ "$conclusion" != "success" ]; then
    echo "La última ejecución ($ejecucion) está en «$estado / $conclusion»: $enlace" >&2
    exit 1
fi

mkdir -p "$SALIDA"
gh run download "$ejecucion" --dir "$TEMPORAL/artefactos"
for lenguaje in python javascript-typescript; do
    sarif="$(find "$TEMPORAL/artefactos/codeql-$lenguaje" -name '*.sarif' | head -1)"
    cp "$sarif" "$SALIDA/codeql_$lenguaje.sarif"
done

{
    echo "fecha: $(date -Is)"
    echo "ejecución: $ejecucion, del $fecha, sobre $commit ($enlace)"
    [ "$commit" = "$(git rev-parse --short=7 HEAD)" ] \
        || echo "  ⚠️ la copia local está en $(git rev-parse --short=7 HEAD), no en $commit"
    python3 -c '
import json, sys
from pathlib import Path
for ruta in sys.argv[1:]:
    herramienta = json.load(open(ruta))["runs"][0]["tool"]["driver"]
    version = herramienta.get("semanticVersion") or herramienta.get("version")
    print(Path(ruta).name + ":", herramienta.get("name"), version)
' "$SALIDA"/codeql_*.sarif
} | tee "$SALIDA/codeql_condiciones.txt"

python3 - "$SALIDA" <<'EOF'
import json
import sys
from collections import Counter
from pathlib import Path

carpeta = Path(sys.argv[1])


def gravedad(numero: float | None) -> str:
    if numero is None:
        return "sin gravedad"
    if numero >= 9:
        return "crítica"
    if numero >= 7:
        return "alta"
    if numero >= 4:
        return "media"
    return "baja"


def donde(ruta: str) -> str:
    if ruta.startswith("backend/evaluation/"):
        return "no servido"
    if ruta.startswith("backend/"):
        return "en la imagen"
    if ruta.startswith("docker/"):
        return "al construir"
    if ruta.startswith("frontend/src/") and not ruta.endswith(".spec.ts"):
        return "en la web"
    return "no servido"


lineas = []
for fichero in sorted(carpeta.glob("codeql_*.sarif")):
    ejecucion = json.loads(fichero.read_text())["runs"][0]
    reglas = {}
    for componente in [ejecucion["tool"]["driver"], *ejecucion["tool"].get("extensions", [])]:
        for regla in componente.get("rules", []):
            numero = (regla.get("properties") or {}).get("security-severity")
            reglas[regla["id"]] = float(numero) if numero is not None else None
    hallazgos = []
    for resultado in ejecucion.get("results", []):
        fisica = resultado["locations"][0]["physicalLocation"]
        ruta = fisica["artifactLocation"]["uri"]
        hallazgos.append((
            gravedad(reglas.get(resultado["ruleId"])),
            donde(ruta),
            resultado["ruleId"],
            f"{ruta}:{fisica.get('region', {}).get('startLine', '?')}",
            resultado["message"]["text"].splitlines()[0][:120],
        ))
    lineas.append(f"== {fichero.name}: {len(hallazgos)} hallazgos")
    for (lugar, nivel), cuantos in sorted(Counter((hallazgo[1], hallazgo[0]) for hallazgo in hallazgos).items()):
        lineas.append(f"   {lugar:13} {nivel:13} {cuantos}")
    for hallazgo in sorted(hallazgos, key=lambda hallazgo: (hallazgo[1], hallazgo[0], hallazgo[3])):
        lineas.append(f"      {hallazgo[1]:13} {hallazgo[0]:13} {hallazgo[2]} · {hallazgo[3]} · {hallazgo[4]}")
(carpeta / "codeql_resumen.txt").write_text("\n".join(lineas) + "\n")
print("\n".join(lineas))
EOF
