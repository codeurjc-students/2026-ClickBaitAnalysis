#!/usr/bin/env bash
# #188 (2026-09-26) - La sesión de GPU alrededor de `spikes/agente_a40.py`.
#
# Abre una sesión en la A40 con `gpu-sesion` —45 min como máximo, y sin el
# túnel hacia la máquina 1, porque la medida va por uno propio desde WSL, en el
# 11500—, deja el 27B cargado, ejecuta el guion de Python aquí, en WSL, y cierra
# la sesión. Al terminar comprueba que la GPU vuelve a 0 MiB y que no queda
# ningún proceso propio en la máquina 2.
#
# Tarda más que los 10 min que aguanta una tarea en segundo plano de Claude
# Code, así que se lanza desacoplado, desde la raíz del repositorio:
#   setsid nohup bash spikes/agente_a40.sh > /tmp/agente_a40.log 2>&1 < /dev/null & disown
# Las partes que se le pasen van al guion de Python (sin ninguna, las tres de
# la primera sesión), y `AGENTE_A40_JSON` dice dónde guardar lo medido. La
# segunda sesión fue:
#   AGENTE_A40_JSON=/tmp/agente_a40_definitiva.json setsid nohup bash spikes/agente_a40.sh definitiva > /tmp/agente_a40_definitiva.log 2>&1 < /dev/null & disown
exec 2>&1
cd "$(dirname "$0")/.." || exit 1
MAQUINA_2=gongarcia@gserver2.tfg.etsii.urjc.es
PUERTO=11500
REGISTRO=$(mktemp -d)
trap 'rm -rf "$REGISTRO"' EXIT

if ! git diff --quiet HEAD -- backend; then
  echo "ABORTADO: backend/ tiene cambios sin commitear; lo medido no sería el commit."
  exit 1
fi

echo "== condiciones"
echo "fecha: $(date -Is) · commit: $(git rev-parse --short HEAD) · rama: $(git branch --show-current) · guion: $(sha256sum spikes/agente_a40.py | cut -c1-12)"

# --- Máquina 2: la sesión, que espera a que WSL termine ---------------------------
{
  cat <<'REMOTO'
cat > /tmp/agente188_sesion.sh <<'SESION'
echo "== máquina 2: el modelo, cargado"
curl -s http://127.0.0.1:11434/api/chat -d '{"model":"qwen3.5:27b","stream":false,"think":false,"keep_alive":"10m","messages":[{"role":"user","content":"Responde sólo: ok"}],"options":{"num_ctx":8192,"num_predict":4}}' \
  | jq -r '"  carga: \(.load_duration/1e9) s · total: \(.total_duration/1e9) s"'
echo "LISTO PARA WSL"
for _ in $(seq 1 2700); do [ -f /tmp/agente188_fin ] && break; sleep 1; done
SESION
rm -f /tmp/agente188_fin
echo "máquina 2: $(hostname) · ollama $(~/.local/ollama/bin/ollama --version 2>&1 | grep -o '[0-9][0-9.]*' | tail -1) · qwen3.5:27b $(sha256sum ~/.ollama/models/manifests/registry.ollama.ai/library/qwen3.5/27b | cut -c1-12) · gpu-sesion $(sha256sum ~/bin/gpu-sesion | cut -c1-12)"
echo "gpu antes: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB · procesos: $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .)"
GPU_SESION_MAX=45m GPU_SESION_TUNEL=0 ~/bin/gpu-sesion bash /tmp/agente188_sesion.sh < /dev/null
sleep 2
echo "== máquina 2, al cerrar la sesión"
echo "  gpu: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB · procesos: $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .) · ollama propios: $(pgrep -u gongarcia -c -x ollama)"
rm -f /tmp/agente188_sesion.sh /tmp/agente188_fin
REMOTO
} | ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$MAQUINA_2" 'bash -s' > "$REGISTRO/maquina2.log" &
LADO_2=$!

until grep -q "LISTO PARA WSL" "$REGISTRO/maquina2.log" 2> /dev/null; do
  kill -0 "$LADO_2" 2> /dev/null || break
  sleep 2
done
cat "$REGISTRO/maquina2.log"

# --- WSL: el túnel propio y la medida ----------------------------------------------
if grep -q "LISTO PARA WSL" "$REGISTRO/maquina2.log"; then
  ssh -f -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
    -L "$PUERTO:127.0.0.1:11434" "$MAQUINA_2"
  # El 11434 de WSL es OTRO Ollama: se comprueba que el 11500 es la A40.
  echo "túnel: 11500 → ollama $(curl -s "http://127.0.0.1:$PUERTO/api/version") · 11434 local → $(curl -s -m 2 http://127.0.0.1:11434/api/version)"
  NLP_BACKEND=local AGENTE_A40_JSON="${AGENTE_A40_JSON:-/tmp/agente_a40.json}" \
    .venv/bin/python spikes/agente_a40.py "$@" < /dev/null
  pkill -f "ssh -f -N .*-L $PUERTO:127.0.0.1:11434" && echo "túnel cerrado"
else
  echo "LA SESIÓN NO SE ABRIÓ: no se mide nada."
fi

# --- Cerrar la sesión y comprobar la GPU -------------------------------------------
ssh -n -o BatchMode=yes "$MAQUINA_2" 'touch /tmp/agente188_fin'
wait "$LADO_2"
sed -n '/== máquina 2, al cerrar/,$p' "$REGISTRO/maquina2.log"
