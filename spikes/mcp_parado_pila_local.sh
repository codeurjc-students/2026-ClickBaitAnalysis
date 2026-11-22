#!/usr/bin/env bash
# #292 (2026-11-14) — R1.8, R3.5, R12.7 y R9.2 en la pila local, con `mcp` parado.
#
# Las pruebas del CI lo cubren con el servidor MCP en proceso y un puerto
# cerrado; esto lo mira en la pila de verdad, con Caddy delante y `mcp` como
# contenedor aparte: parado, su nombre deja de resolverse en la red de Compose,
# que es lo que vería la API en producción.
#
# Tres fases, para poder mirar la pantalla de Sistema entre la primera y la
# segunda:
#
#   subir  levanta la pila de `compose.local.yaml` reconstruyendo las imágenes y,
#          con `mcp` en marcha, ejecuta una señal (200, con sus argumentos) y
#          `analyze_headline` con el titular en blanco (la frase pública).
#   parar  para `mcp` y repite la señal: 503 con una frase pública, no un 500.
#   bajar  lee del historial las dos últimas ejecuciones sueltas, con sus
#          argumentos (R9.2); guarda el registro de la API —muere con el
#          contenedor— y baja la pila.
#
# Ejecutar desde la raíz:  bash spikes/mcp_parado_pila_local.sh subir|parar|bajar
# La salida de cada fase se añade a spikes/mcp_parado_pila_local/salida.txt.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

BASE=(-f compose.yaml -f compose.local.yaml)
SALIDA=spikes/mcp_parado_pila_local
mkdir -p "$SALIDA"
TITULAR='{"arguments": {"headline": "You Will Not Believe What Happened Next"}}'
EN_BLANCO='{"arguments": {"headline": "   "}}'

ejecutar() {
  local herramienta=$1 cuerpo=$2 codigo
  codigo=$(curl -sk -m 60 -o /tmp/mcp_parado_respuesta.json -w '%{http_code}' \
    "https://localhost/api/tools/$herramienta/execute" \
    -H 'Content-Type: application/json' -d "$cuerpo")
  echo "POST /tools/$herramienta/execute -> HTTP $codigo"
  cat /tmp/mcp_parado_respuesta.json
  echo
}

fase() {
  echo "== $1 ($(date '+%Y-%m-%d %H:%M:%S %Z'), $(git rev-parse --short HEAD)$(git diff --quiet || echo ', con cambios sin commitear'))"
}

case "${1:-}" in
  subir)
    {
      docker compose "${BASE[@]}" up --build --wait --quiet-pull 2>&1 | tail -5
      fase "con mcp en marcha"
      ejecutar detect_clickbait_lexical "$TITULAR"
      ejecutar analyze_headline "$EN_BLANCO"
    } | tee -a "$SALIDA/salida.txt"
    ;;
  parar)
    {
      docker compose "${BASE[@]}" stop mcp 2>&1 | tail -2
      fase "con mcp parado"
      ejecutar detect_clickbait_lexical "$TITULAR"
    } | tee -a "$SALIDA/salida.txt"
    ;;
  bajar)
    docker compose "${BASE[@]}" logs --no-color api > /tmp/mcp_parado_api.log
    {
      fase "el historial: las dos últimas ejecuciones sueltas"
      curl -sk -m 30 "https://localhost/api/history?kind=tool&limit=2" |
        python3 -c 'import json, sys
for entrada in json.load(sys.stdin)["items"]:
    print(entrada["tool"], entrada["status"], json.dumps(entrada["payload"].get("arguments")))'
      fase "el registro de la API, antes de bajar"
      # Sin los códigos de color del formato de consola.
      grep -E 'tool.execute.unreachable' /tmp/mcp_parado_api.log | tail -3 |
        sed 's/\x1b\[[0-9;]*m//g' | cut -c1-400
    } | tee -a "$SALIDA/salida.txt"
    docker compose "${BASE[@]}" down 2>&1 | tail -2
    ;;
  *)
    echo "uso: bash spikes/mcp_parado_pila_local.sh subir|parar|bajar" >&2
    exit 2
    ;;
esac
