#!/usr/bin/env bash
# #189 (2026-09-26) - La sesión de GPU alrededor de `spikes/chat_maquina1.py`.
#
# Comprueba que la máquina 1 sirve ESTE commit, mide con la sesión cerrada, abre
# una con `gpu-sesion` —CON su túnel hacia la máquina 1, porque es por donde
# llega la API desplegada; 20 min como máximo—, deja el 27B cargado, mide con
# ella abierta, la cierra, vuelve a medir cerrada y comprueba que la GPU vuelve
# a 0 MiB y que en la máquina 1 no queda nada escuchando en el 11434.
#
# Pasa de los 10 min de una tarea en segundo plano de Claude Code, así que se
# lanza desacoplado, desde la raíz del repositorio:
#   setsid nohup bash spikes/chat_maquina1.sh > /tmp/chat_maquina1.log 2>&1 < /dev/null & disown
exec 2>&1
cd "$(dirname "$0")/.." || exit 1
MAQUINA_1=vmuser@193.147.60.40
MAQUINA_2=gongarcia@gserver2.tfg.etsii.urjc.es
BASE=${CHAT_BASE:-https://gongarcia.tfg.etsii.urjc.es/api}
REGISTRO=$(mktemp -d)
trap 'rm -rf "$REGISTRO"' EXIT

if ! git diff --quiet HEAD -- backend; then
  echo "ABORTADO: backend/ tiene cambios sin commitear; lo medido no sería el commit."
  exit 1
fi

echo "== condiciones"
echo "fecha: $(date -Is) · commit: $(git rev-parse --short HEAD) · rama: $(git branch --show-current) · guion: $(sha256sum spikes/chat_maquina1.py | cut -c1-12)"
DESPLEGADO=$(ssh -n -o BatchMode=yes "$MAQUINA_1" 'cd ~/2026-ClickBaitAnalysis && git rev-parse HEAD')
echo "máquina 1: clon en $(echo "$DESPLEGADO" | cut -c1-7) · rutas del chat servidas: $(curl -sk "$BASE/openapi.json" | grep -o '"/chat[^"]*"\|"/agent"' | sort -u | tr '\n' ' ')"
if [ "$DESPLEGADO" != "$(git rev-parse HEAD)" ]; then
  echo "ABORTADO: la máquina 1 no sirve este commit."
  exit 1
fi

.venv/bin/python spikes/chat_maquina1.py cerrada-antes < /dev/null

# --- Máquina 2: la sesión, con su túnel, que espera a que WSL termine ----------------
{
  cat <<'REMOTO'
cat > /tmp/chat189_sesion.sh <<'SESION'
echo "== máquina 2: el modelo, cargado"
curl -s http://127.0.0.1:11434/api/chat -d '{"model":"qwen3.5:27b","stream":false,"think":false,"keep_alive":"10m","messages":[{"role":"user","content":"Responde sólo: ok"}],"options":{"num_ctx":8192,"num_predict":4}}' \
  | jq -r '"  carga: \(.load_duration/1e9) s · total: \(.total_duration/1e9) s"'
echo "LISTO PARA WSL"
for _ in $(seq 1 1200); do [ -f /tmp/chat189_fin ] && break; sleep 1; done
SESION
rm -f /tmp/chat189_fin
echo "máquina 2: $(hostname) · ollama $(~/.local/ollama/bin/ollama --version 2>&1 | grep -o '[0-9][0-9.]*' | tail -1) · qwen3.5:27b $(sha256sum ~/.ollama/models/manifests/registry.ollama.ai/library/qwen3.5/27b | cut -c1-12) · gpu-sesion $(sha256sum ~/bin/gpu-sesion | cut -c1-12)"
echo "gpu antes: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB · procesos: $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .)"
GPU_SESION_MAX=20m ~/bin/gpu-sesion bash /tmp/chat189_sesion.sh < /dev/null
sleep 2
echo "== máquina 2, al cerrar la sesión"
echo "  gpu: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB · procesos: $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .) · ollama propios: $(pgrep -u gongarcia -c -x ollama) · túneles propios: $(pgrep -u gongarcia -cf '[t]unel_ollama')"
rm -f /tmp/chat189_sesion.sh /tmp/chat189_fin
REMOTO
} | ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$MAQUINA_2" 'bash -s' > "$REGISTRO/maquina2.log" &
LADO_2=$!

until grep -q "LISTO PARA WSL" "$REGISTRO/maquina2.log" 2> /dev/null; do
  kill -0 "$LADO_2" 2> /dev/null || break
  sleep 2
done
cat "$REGISTRO/maquina2.log"

if grep -q "LISTO PARA WSL" "$REGISTRO/maquina2.log"; then
  .venv/bin/python spikes/chat_maquina1.py abierta < /dev/null
else
  echo "LA SESIÓN NO SE ABRIÓ: no se mide nada con ella."
fi

# --- Cerrar la sesión y comprobar ----------------------------------------------------
ssh -n -o BatchMode=yes "$MAQUINA_2" 'touch /tmp/chat189_fin'
wait "$LADO_2"
sed -n '/== máquina 2, al cerrar/,$p' "$REGISTRO/maquina2.log"

# El túnel cae con la sesión: la API tiene que volver a decir que no hay asistente.
sleep 5
.venv/bin/python spikes/chat_maquina1.py cerrada-despues < /dev/null

echo "== máquina 1, al terminar"
ssh -n -o BatchMode=yes "$MAQUINA_1" 'echo "  escuchando en 11434: $(sudo ss -ltnH | awk '"'"'$4 ~ /:11434$/'"'"' | wc -l) · sesiones de tunel: $(pgrep -u tunel -c sshd)"; cd ~/2026-ClickBaitAnalysis && sudo docker compose logs api --since 40m --no-log-prefix 2> /dev/null | grep -E "chat\.(aceptada|imprevisto)|agent\.(vuelta|herramienta|fin)" | sed -E "s/(cliente|trabajo)=[^ ]+/\1=…/" | tail -40'
