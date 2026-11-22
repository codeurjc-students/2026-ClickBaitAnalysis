#!/usr/bin/env bash
# #265 (2026-11-13) - El plan B en la máquina 1: encender las respuestas
# grabadas, reproducirlas desde fuera como lo haría la pantalla y volver a
# Ollama, con lo que tarda cada cambio.
#
# Es `grabado_pila_local.sh` para producción, pero no despliega ni construye
# nada: la imagen de la máquina 1 tiene que llevar ya la grabación («Máquina 1:
# desplegar», en `despliegue/README.md`). Cada cambio recrea sólo la API, con
# `compose.grabado.yaml` o sin él, como en «Máquina 1: el asistente con
# respuestas grabadas»; mientras arranca, tampoco responde el análisis. El
# registro de la API se guarda en la máquina 1 antes de cada cambio, porque
# muere con el contenedor (#191). Termina siempre en Ollama.
#
# Desde la raíz, en WSL. A la máquina 1 se entra por IP: en WSL su huella está
# guardada así, y por nombre SSH responde «Host key verification failed». La
# etiqueta nombra los registros que deja allí (`~/registro-ollama-<etiqueta>.log`
# y `~/registro-grabado-<etiqueta>.log`):
#
#   bash spikes/grabado_maquina1.sh <etiqueta> | tee -a <salida>
#
# Resultado (2026-11-13, la máquina 1 en `835568e`, con la imagen
# `abb28fa257a7`; su salida, en
# `spikes/grabacion_demostracion/2026-11-13-27b/maquina1.txt`): dos pasadas, la
# primera con este mismo guion desde una carpeta temporal y la segunda con éste.
# El cambio a `grabado`, 14 y 13 s; la vuelta a Ollama, 14 s las dos veces; y
# los tres turnos, enteros las dos, con la CPU de la máquina 1. El turno 1 tardó
# 8,1 s la primera vez y 2,1 la segunda: en la primera, el servidor MCP acababa
# de arrancar con el despliegue y cargó en frío los modelos de las señales.
exec 2>&1
cd "$(dirname "$0")/.." || exit 1
ETIQUETA=${1:?Falta la etiqueta de los registros: por ejemplo, el commit desplegado}
MAQUINA_1=vmuser@193.147.60.40
API=https://gongarcia.tfg.etsii.urjc.es/api

agente() {
  curl -sS --max-time 15 "$API/agent" \
    | .venv/bin/python -c 'import json, sys; datos = json.load(sys.stdin); print("  agent:", datos["availability"]["status"], "· recording:", datos["recording"])'
}

# Recrea la API con los ficheros del compose que se le pasen ($1), y dice lo
# que tarda y cómo quedan los servicios. Antes guarda su registro en ~/$2.
cambiar() {
  ssh -T -o BatchMode=yes -o ConnectTimeout=15 "$MAQUINA_1" \
    "cd ~/2026-ClickBaitAnalysis && sudo docker compose logs api > ~/$2 2>&1 < /dev/null; inicio=\$(date +%s); sudo docker compose $1 up -d --wait api < /dev/null > /dev/null 2>&1; echo \"  codigo \$?, \$(( \$(date +%s) - inicio )) s\"; sudo docker compose $1 ps --format '{{.Name}} {{.Status}}' < /dev/null" \
    < /dev/null
}

echo "== $(date -Is) cambio a grabado"
cambiar "-f compose.yaml -f compose.grabado.yaml" "registro-ollama-$ETIQUETA.log"
agente
echo "== $(date -Is) reproducir-en"
.venv/bin/python spikes/grabar_demostracion.py --reproducir-en "$API" 2>&1 \
  | grep -vE "^20..-|Warning|WARNING"
echo "   reproducir-en: ${PIPESTATUS[0]}"
echo "== $(date -Is) vuelta a Ollama"
cambiar "" "registro-grabado-$ETIQUETA.log"
agente
echo "== $(date -Is) FIN"
