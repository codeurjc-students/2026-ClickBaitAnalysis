#!/usr/bin/env bash
# 14 nov 2026 (PR #296) - El precalentado del servidor MCP (PR #295), en la
# máquina 1: redesplegar `dev` y medir el arranque.
#
# Desde la PR #295 el `mcp` del compose precalienta sus modelos en un hilo
# mientras ya atiende, como la API lo hace antes de servir (#125, #267). Lo que
# no se sabía es lo que cuesta en la máquina 1. Esto redespliega y lo mide con
# UNA conexión SSH, como `memoria_maquina1.sh` (#234):
#
# 1. el commit del clon, y el registro de la API ANTES de recrearla —muere con
#    el contenedor (#191)— en `~/registro-antes-<commit nuevo>.log`;
# 2. `git pull --ff-only` y `docker compose up --build --wait`, cronometrado;
# 3. cuándo arrancó la API y cuándo pasó su primera sonda de salud, de las
#    cinco que guarda Docker: con las dos cargas a la vez, la de la API compite
#    por la CPU con la del servidor MCP;
# 4. los eventos `api.preheat` y `mcp.preheat`, con lo que tardó cada modelo;
# 5. la memoria de cada proceso desde `/proc/1/status` (`docker stats` no cuenta
#    lo respaldado por ficheros, #164), con el precalentado ya hecho;
# 6. los registros del arranque, en `~/registro-despliegue-<commit>.log`.
#
# Y desde fuera, por la API pública y Caddy: el primer análisis por el servidor
# MCP (`analyze_headline` por `/tools/{name}/execute`) en inglés y en español,
# otro en inglés ya en caliente, y el titular en blanco, que desde #292 da su
# frase y no el error de Pydantic. Quedan en el historial de producción, como
# las de `produccion_en_vivo.py`.
#
# Despliega: sólo se ejecuta cuando el usuario lo pide. Ejecutar desde la raíz:
#   bash spikes/precalentado_maquina1.sh
# La salida se guarda en spikes/precalentado_maquina1/salida.txt, la medida de
# la PR #296; otro despliegue la guarda en su carpeta, con `SALIDA=<carpeta>`
# (desde #215: el de la congelación, en spikes/congelacion/).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
MAQUINA_1=vmuser@193.147.60.40
SITIO=https://gongarcia.tfg.etsii.urjc.es
SALIDA=${SALIDA:-spikes/precalentado_maquina1}
mkdir -p "$SALIDA"

analizar() {
  local titular=$1 codigo
  codigo=$(curl -s --max-time 120 -o /tmp/precalentado_respuesta.json \
    -w '%{http_code} en %{time_total} s' \
    -X POST "$SITIO/api/tools/analyze_headline/execute" \
    -H 'Content-Type: application/json' \
    -d "{\"arguments\": {\"headline\": \"$titular\"}}")
  printf '«%s» -> HTTP %s · ' "$titular" "$codigo"
  python3 -c 'import json, sys
r = json.load(open("/tmp/precalentado_respuesta.json"))
datos = r.get("data") or {}
print(r.get("status"), datos.get("verdict"), datos.get("language"), r.get("detail") or "", "· argumentos:", json.dumps(r.get("arguments"), ensure_ascii=False))'
}

{
ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$MAQUINA_1" 'bash -s' <<'REMOTO'
desplegar_y_medir() {
  cd ~/2026-ClickBaitAnalysis || exit 1
  antes=$(git rev-parse --short HEAD)
  echo "== $(date -Is) · clon en $antes ($(git branch --show-current)) · cambios sin commitear: $(git status --porcelain | wc -l)"
  git fetch -q origin
  nuevo=$(git rev-parse --short origin/dev)
  if [ "$antes" = "$nuevo" ]; then
    echo "el clon ya está en $nuevo: no hay nada que desplegar"
    exit 1
  fi
  sudo docker compose logs --no-color api > ~/registro-antes-"$nuevo".log 2>&1
  echo "registro de la API de antes: ~/registro-antes-$nuevo.log ($(wc -l < ~/registro-antes-"$nuevo".log) líneas)"
  git pull --ff-only -q || exit 1
  echo
  echo "== despliegue de $(git rev-parse --short HEAD)"
  inicio=$(date +%s)
  sudo docker compose up --build --wait --quiet-pull 2>&1 | tail -3
  echo "up --build --wait: $(( $(date +%s) - inicio )) s, hasta las $(date -Is)"
  echo
  echo "== la API: cuándo arrancó y cuándo pasó su primera sonda de salud"
  id=$(sudo docker compose ps -q api)
  arranque=$(sudo docker inspect -f '{{.State.StartedAt}}' "$id")
  sondas=$(sudo docker inspect -f '{{range .State.Health.Log}}{{.Start.UTC.Format "2006-01-02T15:04:05.000000"}} {{.ExitCode}};{{end}}' "$id")
  python3 - "$arranque" "$sondas" <<'PY'
import sys
from datetime import datetime


def leer(marca):
    # Docker da nanosegundos, y `fromisoformat` admite como mucho microsegundos.
    fecha, _, resto = marca.partition(".")
    fraccion = "".join(caracter for caracter in resto if caracter.isdigit())[:6]
    return datetime.fromisoformat(f"{fecha}.{fraccion or '0'}+00:00")


arranque, sondas = sys.argv[1:]
inicio = leer(arranque)
lista = [sonda.split() for sonda in sondas.split(";") if sonda.strip()]
sanas = [leer(marca) for marca, codigo in lista if codigo == "0"]
print(f"arrancó a las {inicio:%H:%M:%S} UTC; sondas guardadas: {len(lista)}")
if not sanas:
    print("ninguna sana entre las guardadas")
elif lista[0][1] == "0":
    # La más antigua guardada ya era sana: la primera pudo ser antes.
    print(f"sana como tarde a los {(min(sanas) - inicio).total_seconds():.0f} s")
else:
    print(f"primera sonda sana a los {(min(sanas) - inicio).total_seconds():.0f} s")
PY
  echo
  echo "== el precalentado (esperando a mcp.preheat, hasta 300 s)"
  for intento in $(seq 1 60); do
    if sudo docker compose logs --no-color mcp < /dev/null 2>&1 | grep -q 'mcp.preheat'; then
      break
    fi
    sleep 5
  done
  for servicio in api mcp; do
    sudo docker compose logs --no-color "$servicio" < /dev/null 2>&1 \
      | grep "$servicio.preheat" | tail -1 | sed -E 's/^[^|]*\| //; s/\x1b\[[0-9;]*m//g'
  done
  echo
  echo "== memoria de cada proceso, con el precalentado hecho (/proc/1/status, en kB)"
  for servicio in api mcp; do
    printf '%s: ' "$servicio"
    sudo docker compose exec -T "$servicio" sh -c 'grep -E "^(VmRSS|VmHWM|RssAnon|RssFile):" /proc/1/status' < /dev/null \
      | awk '{printf "%s %s · ", $1, $2} END {print ""}'
  done
  echo
  echo "== la máquina (MiB)"
  free -m | sed -n '1,2p'
  echo
  echo "== imágenes"
  sudo docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}} · {{.Size}}' < /dev/null | grep clickbait
  sudo docker compose logs --no-color api mcp > ~/registro-despliegue-"$(git rev-parse --short HEAD)".log 2>&1 < /dev/null
  echo "registros del arranque: ~/registro-despliegue-$(git rev-parse --short HEAD).log"
}
desplegar_y_medir < /dev/null
REMOTO

echo
echo "== el primer análisis por el servidor MCP, desde fuera ($(date -Is))"
analizar "You Will Not Believe What Happened Next"
analizar "No vas a creer lo que pasó después"
echo "-- ya en caliente"
analizar "You Will Not Believe What Happened Next"
echo "-- el titular en blanco (#292)"
analizar "   "
} 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | tee "$SALIDA/salida.txt"
