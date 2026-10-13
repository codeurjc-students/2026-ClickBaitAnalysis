#!/usr/bin/env bash
# #260 · Frente 2 del análisis de vulnerabilidades: las imágenes.
#
# Lo que de verdad corre en producción no es sólo nuestro lockfile: es la
# imagen entera, con su sistema (Debian en el backend, la base de Caddy en la
# web) y los paquetes de cada lenguaje que traiga. Trivy la recorre capa a capa
# y compara cada paquete con sus bases de avisos. Dos pasadas por imagen:
#
#   trivy_<imagen>.json   la que se TRÍA: `--ignore-unfixed` (sólo lo que ya
#                         tiene arreglo publicado) y sólo críticos y altos.
#                         Decidido al definir #260: el resto de una imagen
#                         Debian son cientos de avisos sin arreglo que no se
#                         pueden tratar uno a uno.
#   trivy_recuento.txt    la que sólo se CUENTA: todo, sin filtros, reducido a
#                         una tabla por gravedad, con o sin arreglo y si es del
#                         sistema o de un lenguaje. El JSON entero no se
#                         guarda: de una imagen de 6 GB pesa demasiado.
#
# Sólo `--scanners vuln`: los secretos dentro de la imagen no, porque en 6 GB
# de pesos de modelos sería lento y ruidoso, y los secretos los cubre gitleaks
# sobre el historial de git.
#
# ⚠️ Trivy sufrió un compromiso de su cadena de suministro en marzo de 2026
# (CVE-2026-33634: binario v0.69.4 e imágenes v0.69.5 y v0.69.6 malignas, y
# casi todas las etiquetas de `trivy-action` reescritas). Se usa el binario de
# una release posterior, comprobado con su `checksums.txt`, y nunca su imagen
# de Docker Hub ni su acción. La versión se exige abajo.
#
# Escribe en la carpeta de la comprobación (`spikes/vulnerabilidades/<fecha>
# [-<etiqueta>]/`), la misma que `vulnerabilidades_dependencias.sh`, y se
# niega si ya están sus ficheros. La imagen del backend se comprueba por
# contenido, como allí: su requirements.txt y su torch tienen que ser los del
# repositorio.
#
# Uso, desde la raíz y con Docker sin otra carga (#259):
#   bash spikes/vulnerabilidades_imagenes.sh [etiqueta]
set -euo pipefail
cd "$(dirname "$0")/.."

TRIVY="$HOME/.local/bin/trivy"
TRIVY_VERSION=0.75.0
IMAGENES=(clickbait-backend clickbait-web)
DOCKERFILE=docker/backend.Dockerfile
ETIQUETA="${1:-}"
SALIDA="spikes/vulnerabilidades/$(date +%F)${ETIQUETA:+-$ETIQUETA}"
TEMPORAL="$(mktemp -d)"
trap 'rm -rf "$TEMPORAL"' EXIT

# ── La herramienta, la que se comprobó al instalarla ───────────────────────
if [ "$("$TRIVY" --version 2>/dev/null | head -1)" != "Version: $TRIVY_VERSION" ]; then
    echo "Hace falta Trivy $TRIVY_VERSION en $TRIVY (ver docs/desarrollo.md)." >&2
    exit 1
fi

if [ -e "$SALIDA/trivy_recuento.txt" ]; then
    echo "$SALIDA ya tiene una pasada de imágenes: se pisaría. Dale otra etiqueta." >&2
    exit 1
fi
mkdir -p "$SALIDA"

# ── La imagen del backend tiene que ser la del repositorio ─────────────────
# (la misma comprobación que vulnerabilidades_dependencias.sh)
hash_repositorio="$(sha256sum < requirements.txt | cut -d' ' -f1)"
hash_imagen="$(docker run --rm --network none --entrypoint cat clickbait-backend /app/requirements.txt | sha256sum | cut -d' ' -f1)"
torch_dockerfile="$(grep -oE 'torch==[0-9][0-9.]*' "$DOCKERFILE")"
torch_imagen="$(docker run --rm --network none --entrypoint pip clickbait-backend freeze | grep -i '^torch==')"
if [ "$hash_repositorio" != "$hash_imagen" ] || [ "${torch_imagen%%+*}" != "$torch_dockerfile" ]; then
    echo "La imagen clickbait-backend no es la del repositorio: reconstruirla." >&2
    exit 1
fi

# ── La base de avisos, al día, y sus condiciones ───────────────────────────
"$TRIVY" image --download-db-only --quiet
{
    echo "fecha: $(date -Is)"
    echo "commit: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
    git diff --quiet HEAD -- docker/ requirements.txt frontend/package-lock.json \
        || echo "  ⚠️ con cambios sin commitear en docker/, requirements.txt o el lockfile de npm"
    "$TRIVY" --version
    for imagen in "${IMAGENES[@]}"; do
        echo "imagen: $imagen $(docker image inspect -f '{{.Id}} creada {{.Created}}' "$imagen")"
    done
} | tee "$SALIDA/trivy_condiciones.txt"

# ── Las dos pasadas por imagen ─────────────────────────────────────────────
for imagen in "${IMAGENES[@]}"; do
    echo "== $imagen"
    "$TRIVY" image --quiet --skip-db-update --timeout 30m --scanners vuln \
        --ignore-unfixed --severity CRITICAL,HIGH \
        --format json --output "$SALIDA/trivy_$imagen.json" "$imagen"
    "$TRIVY" image --quiet --skip-db-update --timeout 30m --scanners vuln \
        --format json --output "$TEMPORAL/$imagen.json" "$imagen"
done

# ── El recuento de todo ────────────────────────────────────────────────────
python3 - "$TEMPORAL" "$SALIDA/trivy_recuento.txt" "${IMAGENES[@]}" <<'EOF'
import json
import sys
from collections import Counter
from pathlib import Path

temporal, destino, *imagenes = sys.argv[1:]
GRAVEDADES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
lineas = []
for imagen in imagenes:
    informe = json.loads((Path(temporal) / f"{imagen}.json").read_text())
    sistema = informe.get("Metadata", {}).get("OS", {})
    recuento = Counter()
    distintos = set()
    for resultado in informe.get("Results", []):
        clase = "sistema" if resultado.get("Class") == "os-pkgs" else f"lenguaje ({resultado.get('Type')})"
        for aviso in resultado.get("Vulnerabilities") or []:
            arreglo = "con arreglo" if aviso.get("FixedVersion") else "sin arreglo"
            recuento[(clase, aviso.get("Severity", "UNKNOWN"), arreglo)] += 1
            distintos.add(aviso["VulnerabilityID"])
    lineas.append(f"== {imagen} · {sistema.get('Family')} {sistema.get('Name')} · {len(distintos)} avisos distintos")
    for clase in sorted({clave[0] for clave in recuento}):
        for arreglo in ("con arreglo", "sin arreglo"):
            fila = [f"{gravedad} {recuento[(clase, gravedad, arreglo)]}" for gravedad in GRAVEDADES if recuento[(clase, gravedad, arreglo)]]
            if fila:
                lineas.append(f"   {clase:28} {arreglo:12} {', '.join(fila)}")
Path(destino).write_text("\n".join(lineas) + "\n")
print("\n".join(lineas))
EOF

# ── Lo que se tría ─────────────────────────────────────────────────────────
for imagen in "${IMAGENES[@]}"; do
    python3 - "$SALIDA/trivy_$imagen.json" "$imagen" <<'EOF'
import json
import sys

informe = json.load(open(sys.argv[1]))
avisos = [
    (resultado.get("Target"), aviso)
    for resultado in informe.get("Results", [])
    for aviso in resultado.get("Vulnerabilities") or []
]
print(f"== {sys.argv[2]}: {len(avisos)} críticos o altos con arreglo")
for objetivo, aviso in avisos:
    print(f"   {aviso['Severity']:8} {aviso['PkgName']} {aviso['InstalledVersion']} -> {aviso.get('FixedVersion')} · {aviso['VulnerabilityID']} · {objetivo}")
EOF
done
