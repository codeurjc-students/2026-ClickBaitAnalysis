#!/usr/bin/env bash
# #191 (2026-09-28) - Lo que dejó el agente en el registro de la API desplegada.
#
# Cada conversación aceptada, cada vuelta del modelo —qué herramientas pidió,
# `prompt_tokens` y tiempo— y cada herramienta con su duración, sacado de los
# eventos `chat.*` y `agent.*` que escribe la API. Sirve para contar cómo fue
# una prueba hecha A MANO en producción, desde el navegador, sin tener que
# guardar nada allí. El id de cada conversación y la IP del cliente se tapan.
#
# Ojo: el registro es del CONTENEDOR y se pierde al recrearlo, o sea, en cada
# redespliegue. Lo que se quiera citar se lee antes del siguiente.
#
# Ejecutar desde WSL, con dos fechas que entienda `docker compose logs`:
#   bash spikes/chat_registro.sh 2026-09-28T18:22:00Z 2026-09-28T18:24:00Z
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
  sudo docker compose logs api --since "$DESDE" ${HASTA:+--until "$HASTA"} --no-log-prefix --no-color 2> /dev/null \
    | grep -E "chat\.(aceptada|imprevisto)|agent\.(vuelta|herramienta|fin)" \
    | sed -E 's/\x1b\[[0-9;]*m//g; s/(trabajo|cliente)=[^ ]+/\1=…/g; s/^([0-9-]+T[0-9:]+)\.[0-9]+Z/\1Z/' \
    | tr -s ' '
}
leer < /dev/null
REMOTO
