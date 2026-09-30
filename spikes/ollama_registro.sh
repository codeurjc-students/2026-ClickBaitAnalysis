#!/usr/bin/env bash
# #193 (2026-09-30) - Lo que dejó Ollama en su registro durante una sesión de GPU.
#
# Complementa a `chat_registro.sh`, que lee la API. Aquí sale lo que la API no
# ve: cuánto tardó el servidor en responder desde que arrancó, si la primera
# conversación tuvo que cargar el modelo y cuánto le costó, y lo que tardó cada
# `POST /api/chat` dentro de Ollama. Cada `GET /api/tags` es una comprobación
# de disponibilidad de la API (`GET /agent` o `POST /chat`); `gpu-sesion` sólo
# pregunta `/api/version`, que no se enseña. Sólo lee un fichero: no toca la GPU.
#
# Ojo: `gpu-sesion` escribe ese registro con `>`, así que cada sesión borra el
# de la anterior. Lo que se quiera citar se lee antes de abrir la siguiente.
#
# Ejecutar desde WSL:
#   bash spikes/ollama_registro.sh
exec 2>&1
MAQUINA_2=gongarcia@gserver2.tfg.etsii.urjc.es

ssh -T -o BatchMode=yes "$MAQUINA_2" 'bash -s' <<'REMOTO'
leer() {
  local registro=~/.ollama-serve.log
  echo "registro: modificado $(date -r "$registro" '+%F %T %z') · $(wc -l < "$registro") líneas"
  grep -E 'msg="(Listening on|inference compute|llama-server GPU discovery watchdog timed out|loading model via llama-server|llama-server started in)|"/api/(tags|chat)"' "$registro" \
    | sed -E 's/^time=([^ ]+) level=[A-Z]+ source=[^ ]+ (msg="[^"]*").*/\1 \2/' \
    | tr -s ' ' \
    | uniq
}
leer < /dev/null
REMOTO
