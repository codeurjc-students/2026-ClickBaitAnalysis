#!/usr/bin/env bash
# #260 · Frente 3 del análisis de vulnerabilidades: el código, con las reglas S
# de ruff.
#
# Las reglas `S` son las de Bandit reimplementadas en ruff: patrones que a
# menudo son peligrosos (SQL montado con cadenas, `subprocess`, `yaml.load`,
# `random` para criptografía, escuchar en 0.0.0.0, `assert`…). Cada aviso es una
# pregunta, no un fallo demostrado: se tría leyendo el código.
#
# Una pasada, no una regla del CI (decidido al definir #260): `ruff.toml` no
# cambia, y con `--exit-zero` un aviso no hace fallar el guion. Escribe en la
# carpeta de la comprobación (`spikes/vulnerabilidades/<fecha>[-<etiqueta>]/`):
#
#   ruff_s.json          todos los avisos, con la ruta relativa a la raíz
#   ruff_s_resumen.txt   por regla y carpeta, separando lo que va en la imagen
#                        (`backend/` sin `evaluation/`, que el .dockerignore deja
#                        fuera), lo que sólo corre al construirla (`docker/`) y
#                        lo que no se sirve (`tests/`, `backend/evaluation/`…)
#
# `--force-exclude` respeta las exclusiones de `ruff.toml` (spikes/, .venv/,
# data/) aunque se le pase una ruta. Se niega si ya están sus ficheros.
#
# Uso, desde la raíz:
#   bash spikes/vulnerabilidades_codigo.sh [etiqueta]
set -euo pipefail
cd "$(dirname "$0")/.."

RUFF=(.venv/bin/python -m ruff)
ETIQUETA="${1:-}"
SALIDA="spikes/vulnerabilidades/$(date +%F)${ETIQUETA:+-$ETIQUETA}"

if [ -e "$SALIDA/ruff_s.json" ]; then
    echo "$SALIDA ya tiene una pasada de código: se pisaría. Dale otra etiqueta." >&2
    exit 1
fi
mkdir -p "$SALIDA"

{
    echo "fecha: $(date -Is)"
    echo "commit: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
    git diff --quiet HEAD -- '*.py' || echo "  ⚠️ con cambios sin commitear en ficheros .py"
    echo "$("${RUFF[@]}" --version), reglas S, --force-exclude"
} | tee "$SALIDA/ruff_s_condiciones.txt"

"${RUFF[@]}" check --select S --force-exclude --exit-zero --output-format json . \
    > "$SALIDA/ruff_s_crudo.json"

python3 - "$SALIDA" "$(pwd)" <<'EOF'
import json
import sys
from collections import Counter
from pathlib import Path

carpeta, raiz = Path(sys.argv[1]), Path(sys.argv[2])
crudos = json.loads((carpeta / "ruff_s_crudo.json").read_text())


def donde(ruta: str) -> str:
    if ruta.startswith("backend/evaluation/"):
        return "no servido"
    if ruta.startswith("backend/"):
        return "en la imagen"
    if ruta.startswith("docker/"):
        return "al construir"
    return "no servido"


avisos = []
for crudo in crudos:
    ruta = str(Path(crudo["filename"]).resolve().relative_to(raiz))
    avisos.append({
        "regla": crudo["code"],
        "ruta": ruta,
        "fila": crudo["location"]["row"],
        "mensaje": crudo["message"],
        "donde": donde(ruta),
    })
(carpeta / "ruff_s.json").write_text(json.dumps(avisos, indent=1, ensure_ascii=False) + "\n")
(carpeta / "ruff_s_crudo.json").unlink()

lineas = [f"{len(avisos)} avisos"]
for lugar in ("en la imagen", "al construir", "no servido"):
    del_lugar = [aviso for aviso in avisos if aviso["donde"] == lugar]
    lineas.append(f"\n== {lugar}: {len(del_lugar)}")
    por_regla_y_carpeta = Counter((aviso["regla"], str(Path(aviso["ruta"]).parent)) for aviso in del_lugar)
    for (regla, directorio), cuantos in sorted(por_regla_y_carpeta.items()):
        lineas.append(f"   {regla:6} {cuantos:5}  {directorio}/")
    if lugar != "no servido":
        for aviso in del_lugar:
            lineas.append(f"      {aviso['ruta']}:{aviso['fila']} {aviso['regla']} {aviso['mensaje']}")
(carpeta / "ruff_s_resumen.txt").write_text("\n".join(lineas) + "\n")
print("\n".join(lineas))
EOF
