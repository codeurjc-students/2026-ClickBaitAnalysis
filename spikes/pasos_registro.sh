#!/usr/bin/env bash
# #214 (2026-11-15) - Qué hizo la pantalla, y cuándo, durante una prueba a mano.
#
# Complementa a `chat_registro.sh`, que cuenta lo que hizo el agente: aquí sale
# cada petición de la web que marca un paso de la demostración
# (`docs/demostracion.md`), con su hora. Con la hora a la que empezó una
# grabación, da el minuto de cada paso en el vídeo sin tener que verlo. La IP
# del cliente se tapa.
#
#   POST /api/analyze        un análisis (pasos 1 a 3)
#   GET  /api/history?…      la pantalla de Historial (paso 4)
#   GET  /api/history/<id>   abrir un análisis guardado
#   GET  /api/tools          la pantalla de Sistema (paso 5); sólo la pide ella
#   POST /api/chat           una pregunta al asistente (pasos 6 y 7)
#
# La hora la pone `docker compose logs --timestamps`, porque la línea de acceso
# de uvicorn no la lleva. Es cuando la API recibió la petición, o sea, el clic
# del botón, y no cuando se empezó a hablar del paso.
#
# Ojo: el registro es del CONTENEDOR y se pierde al recrearlo: en cada
# redespliegue, y también al pasar al plan B y al volver. Lo que se quiera citar
# se lee antes.
#
# Ejecutar desde WSL, con dos fechas que entienda `docker compose logs`:
#   bash spikes/pasos_registro.sh 2026-11-15T12:21:30Z 2026-11-15T12:46:00Z
# Sin fechas, los últimos 30 minutos.
exec 2>&1
MAQUINA_1=vmuser@193.147.60.40
DESDE=${1:-30m}
HASTA=${2:-}

ssh -T -o BatchMode=yes "$MAQUINA_1" "DESDE='$DESDE' HASTA='$HASTA' bash -s" <<'REMOTO'
leer() {
  cd ~/2026-ClickBaitAnalysis || return 1
  echo "clon: $(git branch --show-current) · $(git log --oneline -1 | cut -c1-70)"
  echo "contenedor de la API creado: $(sudo docker inspect -f '{{.Created}}' clickbait-api-1 | cut -c1-19)Z"
  sudo docker compose logs api --timestamps --since "$DESDE" ${HASTA:+--until "$HASTA"} --no-log-prefix --no-color 2> /dev/null \
    | grep -E '"(POST /api/analyze|GET /api/history|GET /api/tools|POST /api/chat)[ ?/]' \
    | sed -E 's/\x1b\[[0-9;]*m//g; s/^([0-9-]+T[0-9:]+)\.[0-9]+Z/\1Z/; s/[0-9]{1,3}(\.[0-9]{1,3}){3}(:[0-9]+)?/IP/g' \
    | tr -s ' '
}
leer < /dev/null
REMOTO
