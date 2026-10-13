#!/usr/bin/env bash
# #260 · Frente 4 del análisis de vulnerabilidades: secretos en el historial.
#
# Un secreto que entró en un commit sigue en el historial aunque el fichero se
# borre después: en un repositorio público, cualquiera puede leerlo. gitleaks
# recorre TODAS las confirmaciones de todas las ramas (`--log-opts=--all`,
# también las de `origin/`) y busca con su configuración por defecto lo que
# parece una clave: patrones conocidos (GitHub, AWS, Hugging Face…) y cadenas
# de mucha entropía.
#
# Sólo el historial de git, no la carpeta: escanearla encontraría las claves de
# verdad del `.env`, que está en `.gitignore` y no ha salido nunca, y las
# pondría en un informe sin aportar nada.
#
# `--redact`: el secreto sale como REDACTED en todo lo que escribe gitleaks. El
# informe completo sólo vive en una carpeta temporal; a la carpeta de la
# comprobación va recortado:
#
#   gitleaks.json            regla, fichero, línea, commit, fecha y huella de
#                            cada hallazgo; sin autor, correo ni mensaje del
#                            commit (no hacen falta para triar) y sin el
#                            secreto, aunque ya vaya tapado
#   gitleaks_resumen.txt     cada hallazgo y si su fichero sigue existiendo
#                            hoy: una clave que sólo está en un commit viejo no
#                            se arregla borrándola, sino ROTÁNDOLA
#   gitleaks_condiciones.txt la versión, el commit y cuántas confirmaciones
#
# Control: debería salir la clave que se filtró en la Fase A (README, «1.1 —
# Incidente: filtración de API key y rotación»), ya rotada. Se niega si ya
# están sus ficheros.
#
# Uso, desde la raíz:
#   bash spikes/vulnerabilidades_secretos.sh [etiqueta]
set -euo pipefail
cd "$(dirname "$0")/.."

GITLEAKS="$HOME/.local/bin/gitleaks"
GITLEAKS_VERSION=8.30.1
ETIQUETA="${1:-}"
SALIDA="spikes/vulnerabilidades/$(date +%F)${ETIQUETA:+-$ETIQUETA}"
TEMPORAL="$(mktemp -d)"
trap 'rm -rf "$TEMPORAL"' EXIT

if [ "$("$GITLEAKS" version 2>/dev/null)" != "$GITLEAKS_VERSION" ]; then
    echo "Hace falta gitleaks $GITLEAKS_VERSION en $GITLEAKS (ver docs/desarrollo.md)." >&2
    exit 1
fi
if [ -e "$SALIDA/gitleaks.json" ]; then
    echo "$SALIDA ya tiene una pasada de secretos: se pisaría. Dale otra etiqueta." >&2
    exit 1
fi
mkdir -p "$SALIDA"

ls .gitleaks.toml > /dev/null 2>&1 && configuracion=".gitleaks.toml" || configuracion="la de por defecto"
{
    echo "fecha: $(date -Is)"
    echo "commit: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
    echo "gitleaks $GITLEAKS_VERSION, configuración: $configuracion, --redact"
    if [ -e .gitleaksignore ]; then
        echo ".gitleaksignore: $(grep -cvE '^\s*(#|$)' .gitleaksignore) huellas ya triadas"
    else
        echo ".gitleaksignore: no hay"
    fi
    echo "confirmaciones en todas las ramas: $(git rev-list --all --count)"
} | tee "$SALIDA/gitleaks_condiciones.txt"

"$GITLEAKS" git . --log-opts="--all" --redact --no-banner --exit-code 0 \
    --report-format json --report-path "$TEMPORAL/informe.json" 2>&1 \
    | grep -vE '^\s*$' | tail -3

python3 - "$TEMPORAL/informe.json" "$SALIDA" <<'EOF'
import json
import subprocess
import sys
from pathlib import Path

informe, carpeta = Path(sys.argv[1]), Path(sys.argv[2])
hallazgos = [
    {
        "regla": crudo["RuleID"],
        "descripcion": crudo.get("Description"),
        "fichero": crudo["File"],
        "linea": crudo["StartLine"],
        "commit": crudo["Commit"][:7],
        "fecha": crudo.get("Date", "")[:10],
        "huella": crudo.get("Fingerprint"),
    }
    for crudo in json.loads(informe.read_text())
]
hallazgos.sort(key=lambda hallazgo: (hallazgo["fecha"], hallazgo["fichero"], hallazgo["linea"]))
(carpeta / "gitleaks.json").write_text(json.dumps(hallazgos, indent=1, ensure_ascii=False) + "\n")

seguidos = set(subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n"))
lineas = [f"{len(hallazgos)} hallazgos"]
for hallazgo in hallazgos:
    sigue = "sigue en HEAD" if hallazgo["fichero"] in seguidos else "ya no está en HEAD"
    lineas.append(
        f"   {hallazgo['fecha']} {hallazgo['commit']} {hallazgo['regla']:28} "
        f"{hallazgo['fichero']}:{hallazgo['linea']} · {sigue}"
    )
(carpeta / "gitleaks_resumen.txt").write_text("\n".join(lineas) + "\n")
print("\n".join(lineas))
EOF
