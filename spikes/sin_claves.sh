#!/bin/bash
# ¿Arranca el sistema sin ninguna clave de API? (#259)
#
#   bash spikes/sin_claves.sh
#
# Copia la copia de trabajo a /tmp/sin-claves SIN `.env` y levanta con Docker
# `api` y `mcp` sin ninguna variable de clave. `web` no: con `compose.yaml` solo
# necesita el certificado de la máquina 1, y no es lo que se mide (la variante
# para otra máquina, `compose.local.yaml`, llega con #251). Comprueba:
#
#   - que los dos quedan sanos (`--wait`);
#   - el aviso del arranque en el registro de los dos;
#   - `/health`, con Guardian y NYT «no configurada» y sin preguntarles;
#   - un `POST /analyze`, que no usa ninguna clave;
#   - y que `get_guardian_news`, por MCP, dice qué falta.
#
# Al terminar, `down` (el volumen del historial se conserva). Lo de dentro del
# contenedor se pregunta con su Python, porque la imagen no trae curl.
#
# Resultados del 12 oct 2026, en la sección de #259 del README.

set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
COPIA=/tmp/sin-claves
inicio=$(date +%s)
paso() { echo; echo "=== $(( $(date +%s) - inicio )) s · $*"; }

paso "la copia, sin .env"
rm -rf "$COPIA"
rsync -a --exclude .env --exclude .git --exclude .venv --exclude node_modules "$REPO/" "$COPIA/"
cd "$COPIA" || exit 1
ls .env 2> /dev/null && { echo "hay un .env: no se mide"; exit 1; }
docker --version; docker compose version

paso "arrancar api y mcp sin claves"
t0=$(date +%s)
env -u GUARDIAN_API_KEY -u NYT_API_KEY -u HF_TOKEN -u GNEWS_API_KEY -u NEWSDATA_API_KEY \
  docker compose up --build --wait api mcp < /dev/null > /tmp/sin_claves_compose.txt 2>&1
codigo=$?
echo "--- código $codigo: docker compose up --build --wait api mcp, en $(( $(date +%s) - t0 )) s"
tail -4 /tmp/sin_claves_compose.txt
docker compose ps --format '  {{.Service}}: {{.Status}}' < /dev/null
# Si no quedó sano, el porqué está en su registro, que `down` borra.
if [ "$codigo" != 0 ]; then
  docker compose logs --no-color api < /dev/null | tail -15 | cut -c1-200
  free -m | sed -n '1,2p'
fi

paso "el aviso del arranque"
docker compose logs --no-color api mcp < /dev/null | grep claves_sin_configurar | cut -c1-220

paso "dentro de la API"
# El programa llega por la entrada del `exec`: un heredoc, y no `python -c`, para
# no pelear con las comillas.
docker compose exec -T api python - <<'PY'
import json
import urllib.request


def pedir(ruta, cuerpo=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(
        "http://127.0.0.1:8000" + ruta,
        data=datos,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:
        return respuesta.status, json.load(respuesta)


codigo, salud = pedir("/health")
print("  GET /health ->", codigo, salud["status"], salud["integrations"])

titular = {"headline": "You Will Never Believe What This Cat Did Next"}
codigo, analisis = pedir("/analyze", titular)
print("  POST /analyze ->", codigo, analisis["analysis"]["verdict"])
for senal in analisis["analysis"]["signals"]:
    print(f"    {senal['name']:30} {senal['status']}")

argumentos = {"arguments": {"topic": "technology"}}
codigo, ejecucion = pedir("/tools/get_guardian_news/execute", argumentos)
print("  get_guardian_news por MCP ->", codigo, ejecucion["status"], ejecucion.get("detail"))
PY

paso "parar"
docker compose down < /dev/null > /dev/null 2>&1; echo "--- código $?: docker compose down"
cd / && rm -rf "$COPIA"
echo
echo "FIN en $(( $(date +%s) - inicio )) s"
