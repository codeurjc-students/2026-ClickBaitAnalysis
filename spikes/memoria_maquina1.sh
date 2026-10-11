#!/usr/bin/env bash
# #234 (2026-10-10) - ¿Cuánto ocupan, en la máquina 1, la imagen y la memoria
# de la API y del MCP con los modelos de los dos idiomas?
#
# `v0.8` añade dos modelos horneados (BETO, #242, y el tono en español, #233),
# unos 980 MB de pesos, y la API los precalienta todos al arrancar. Esto lo
# mide con UNA conexión SSH, como #164: el commit del clon, el estado de los
# servicios, el precalentado de la API (su evento `api.preheat`), el tamaño de
# las imágenes, la memoria de cada proceso desde `/proc/1/status` dentro de su
# contenedor —`docker stats` engaña: no cuenta lo respaldado por ficheros
# (#164)— y la de la máquina.
#
# El MCP no precalienta: carga cada modelo la primera vez que se usa. Para
# medirlo con todo cargado, ejecutar ANTES `spikes/produccion_en_vivo.py`, que
# pasa por el MCP todas las señales con un titular en inglés y otro en español.
#
# Ejecutar desde la raíz:
#   bash spikes/memoria_maquina1.sh
exec 2>&1
MAQUINA_1=vmuser@193.147.60.40

ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$MAQUINA_1" 'bash -s' <<'REMOTO'
medir() {
  cd ~/2026-ClickBaitAnalysis || exit 1
  echo "== $(date -Is) · clon en $(git rev-parse --short HEAD) · cambios sin commitear: $(git status --porcelain | wc -l)"
  echo
  echo "== servicios"
  sudo docker compose ps --format '{{.Service}}: {{.State}} · {{.Status}}' < /dev/null
  echo
  echo "== precalentado de la API (último arranque)"
  sudo docker compose logs --no-color api < /dev/null 2>&1 | grep 'api.preheat' | tail -1 | sed -E 's/^[^|]*\| //; s/\x1b\[[0-9;]*m//g'
  echo
  echo "== imágenes"
  sudo docker image ls --format '{{.Repository}}:{{.Tag}} · {{.Size}} · creada {{.CreatedSince}}' < /dev/null | grep clickbait
  echo
  echo "== memoria de cada proceso (/proc/1/status, en kB)"
  for servicio in api mcp; do
    printf '%s: ' "$servicio"
    sudo docker compose exec -T "$servicio" sh -c 'grep -E "^(VmRSS|VmHWM|RssAnon|RssFile):" /proc/1/status' < /dev/null \
      | awk '{printf "%s %s · ", $1, $2} END {print ""}'
  done
  echo
  echo "== la máquina (MiB)"
  free -m | sed -n '1,2p'
}
medir < /dev/null
REMOTO
