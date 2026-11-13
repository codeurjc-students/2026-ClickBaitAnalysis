#!/usr/bin/env bash
# #265 (2026-11-13) - El plan B en la pila local: encender las respuestas
# grabadas, reproducirlas por la API y volver a Ollama, con lo que tarda cada
# cambio.
#
# Levanta la pila de `compose.local.yaml` reconstruyendo las imágenes, pasa la
# API a `grabado` con `compose.grabado.yaml`, reproduce la grabación por la API
# como la pantalla (`grabar_demostracion.py --reproducir-en`) y vuelve a Ollama.
# El registro de la API se guarda antes de cada cambio, porque muere con el
# contenedor (#191). No baja la pila al terminar.
#
# La grabación tiene que estar en `backend/integrations/llm/grabaciones/` ANTES
# de construir, porque va dentro de la imagen (`COPY backend/`): sin ella, la API
# en `grabado` dice que no se puede usar. Tarda más que los 10 min de una tarea
# en segundo plano de Claude Code si hay que construir en frío; desacoplado,
# desde la raíz:
#
#   setsid nohup bash spikes/grabado_pila_local.sh > /tmp/grabado_pila_local.log 2>&1 < /dev/null & disown
#
# Resultado (2026-11-13, la rama de #265 sin commitear sobre `637affd`, con la
# toma 1 del 2B de `spikes/grabacion_demostracion/2026-11-13-2b/`; su salida,
# en `pila_local.txt` de esa carpeta): la pila, arriba en 133 s; el cambio a
# `grabado`, 20 s; los tres turnos, enteros (8, 2 y 2 s); y la vuelta a Ollama,
# 21 s. Cada cambio recrea sólo la API, y es casi todo su arranque: el
# precalentado de los modelos y el healthcheck.
exec 2>&1
cd "$(dirname "$0")/.." || exit 1
GRABACION=backend/integrations/llm/grabaciones/demostracion.json
BASE="-f compose.yaml -f compose.local.yaml"
GRABADO="$BASE -f compose.grabado.yaml"

if [ ! -f "$GRABACION" ]; then
  echo "ABORTADO: falta $GRABACION, y la imagen se construiría sin ella."
  exit 1
fi

segundos() { echo $(( $(date +%s) - $1 )); }
agente() {
  curl -sk -m 10 https://localhost/api/agent \
    | .venv/bin/python -c 'import json, sys; datos = json.load(sys.stdin); print("  agent:", datos["availability"]["status"], "· recording:", datos["recording"])'
}

echo "== $(date -Is) commit $(git rev-parse --short HEAD), grabación $(sha256sum "$GRABACION" | cut -c1-12)"
inicio=$(date +%s)
docker compose $BASE up --build --wait --quiet-pull
echo "== pila arriba, con Ollama: $(segundos "$inicio") s"
agente
docker compose $BASE logs api > /tmp/grabado_pila_api_1.log

echo "== cambio a grabado"
inicio=$(date +%s)
docker compose $GRABADO up -d --wait api
echo "== cambio: $(segundos "$inicio") s"
agente
.venv/bin/python spikes/grabar_demostracion.py --reproducir-en https://localhost/api 2>&1 \
  | grep -vE "^20..-|Warning|WARNING"
echo "   reproducir-en: ${PIPESTATUS[0]}"
docker compose $GRABADO logs api > /tmp/grabado_pila_api_2.log

echo "== vuelta a Ollama"
inicio=$(date +%s)
docker compose $BASE up -d --wait api
echo "== vuelta: $(segundos "$inicio") s"
agente
echo "FIN"
