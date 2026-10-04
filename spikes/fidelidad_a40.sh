#!/usr/bin/env bash
# #192 (2026-09-29) - La sesión de GPU alrededor de `spikes/fidelidad.py`.
#
# El patrón de `spikes/agente_a40.sh`, aparte para no tocar el guion que
# respalda las cifras de #188: abre una sesión en la A40 con `gpu-sesion` —45
# min como máximo, y sin el túnel hacia la máquina 1, porque la medida va por
# uno propio desde WSL, en el 11500—, deja un modelo cargado, ejecuta el guion
# de Python aquí, en WSL, y cierra la sesión. Al terminar comprueba que la GPU
# vuelve a 0 MiB y que no queda ningún proceso propio en la máquina 2.
#
# Qué modelo precarga depende de la parte: para `corpus`, el 27B con 8192 de
# ventana (el 2B se carga cuando le toca, y su carga queda en el `load_s` de su
# primera vuelta); para `jueces`, el juez con 16384, que es el `JUEZ_NUM_CTX`
# de `fidelidad.py`. Con otra ventana, Ollama volvería a cargar el modelo en la
# primera petición.
#
# Se niega a medir si lo que la medida usa tiene cambios sin commitear: lo
# medido tiene que ser un commit. (En #188 la primera sesión corrió el guion
# antes de commitearlo, y hubo que explicarlo en el README.) Para `jueces`,
# también la rúbrica y el corpus que se juzga.
#
# Tarda más que los 10 min que aguanta una tarea en segundo plano de Claude
# Code, así que se lanza desacoplado, desde la raíz del repositorio. Los
# argumentos van al guion de Python: la parte y, si se quiere, las fuentes, o
# el juez. Un juez que no quepa en una sesión continúa en la siguiente.
#   setsid nohup bash spikes/fidelidad_a40.sh corpus > /tmp/fidelidad_corpus.log 2>&1 < /dev/null & disown
#   setsid nohup bash spikes/fidelidad_a40.sh jueces gpt-oss:20b > /tmp/fidelidad_juez.log 2>&1 < /dev/null & disown
#   setsid nohup bash spikes/fidelidad_a40.sh comparar A B C D > /tmp/fidelidad_comparar.log 2>&1 < /dev/null & disown
#   setsid nohup bash spikes/fidelidad_a40.sh jueces gemma4:31b comparacion-C-05.json > /tmp/fidelidad_juez.log 2>&1 < /dev/null & disown
#
# #208 (2026-10-04): `repeticion`, `seguimiento` y `ventana` precargan el 27B con
# 16384, la ventana de producción desde #192. Y la sesión dura FIDELIDAD_MINUTOS
# (45 por defecto): la repetición de las desbocadas no cabe en 45.
#   FIDELIDAD_MINUTOS=60 setsid nohup bash spikes/fidelidad_a40.sh repeticion desbocadas > /tmp/fidelidad_rep.log 2>&1 < /dev/null & disown
exec 2>&1
cd "$(dirname "$0")/.." || exit 1
MAQUINA_2=gongarcia@gserver2.tfg.etsii.urjc.es
PUERTO=11500
REGISTRO=$(mktemp -d)
trap 'rm -rf "$REGISTRO"' EXIT
MINUTOS=${FIDELIDAD_MINUTOS:-45}

USADO=(backend spikes/fidelidad.py)
if [ "${1:-}" = jueces ]; then
  PRECARGA=${2:?falta el modelo juez: fidelidad_a40.sh jueces <modelo>}
  CTX=16384
  # Lo juzgado: el corpus, o el fichero de la comparación que se le pase.
  USADO+=(spikes/prompts/juez-fidelidad.md "spikes/fidelidad/${3:-corpus.json}")
elif [[ "${1:-}" =~ ^(repeticion|seguimiento|ventana)$ ]]; then
  PRECARGA=qwen3.5:27b
  CTX=16384
else
  PRECARGA=qwen3.5:27b
  CTX=8192
fi
for fichero in "${USADO[@]}"; do
  if ! git ls-files --error-unmatch "$fichero" > /dev/null 2>&1 || ! git diff --quiet HEAD -- "$fichero"; then
    echo "ABORTADO: $fichero no está commiteado tal cual; lo medido no sería el commit."
    exit 1
  fi
done

echo "== condiciones"
echo "fecha: $(date -Is) · commit: $(git rev-parse --short HEAD) · rama: $(git branch --show-current) · guion: $(sha256sum spikes/fidelidad.py | cut -c1-12) · precarga: $PRECARGA con num_ctx $CTX · sesión: $MINUTOS min"

# --- Máquina 2: la sesión, que espera a que WSL termine ---------------------------
{
  # El resto va entre comillas, sin expandir aquí: el modelo y la ventana se le
  # pasan delante, como variables del guion remoto, que las hereda la sesión.
  printf 'export PRECARGA=%q CTX=%q MINUTOS=%q\n' "$PRECARGA" "$CTX" "$MINUTOS"
  cat <<'REMOTO'
cat > /tmp/fidelidad192_sesion.sh <<'SESION'
echo "== máquina 2: $PRECARGA, cargado"
jq -nc --arg modelo "$PRECARGA" --argjson ctx "$CTX" \
  '{model: $modelo, stream: false, keep_alive: "10m", messages: [{role: "user", content: "Responde sólo: ok"}], options: {num_ctx: $ctx, num_predict: 4}}' \
  | curl -s http://127.0.0.1:11434/api/chat -d @- \
  | jq -r '"  carga: \((.load_duration // 0) / 1e9) s · total: \((.total_duration // 0) / 1e9) s\(if .error then " · ERROR: " + .error else "" end)"'
echo "LISTO PARA WSL"
for _ in $(seq 1 $((MINUTOS * 60))); do [ -f /tmp/fidelidad192_fin ] && break; sleep 1; done
SESION
rm -f /tmp/fidelidad192_fin
biblioteca=~/.ollama/models/manifests/registry.ollama.ai/library
echo "máquina 2: $(hostname) · ollama $(~/.local/ollama/bin/ollama --version 2>&1 | grep -o '[0-9][0-9.]*' | tail -1) · $PRECARGA $(sha256sum "$biblioteca/${PRECARGA%%:*}/${PRECARGA#*:}" | cut -c1-12) · qwen3.5:2b $(sha256sum $biblioteca/qwen3.5/2b | cut -c1-12) · gpu-sesion $(sha256sum ~/bin/gpu-sesion | cut -c1-12)"
echo "gpu antes: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB · procesos: $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .)"
GPU_SESION_MAX=${MINUTOS}m GPU_SESION_TUNEL=0 ~/bin/gpu-sesion bash /tmp/fidelidad192_sesion.sh < /dev/null
sleep 2
echo "== máquina 2, al cerrar la sesión"
echo "  gpu: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB · procesos: $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .) · ollama propios: $(pgrep -u gongarcia -c -x ollama)"
rm -f /tmp/fidelidad192_sesion.sh /tmp/fidelidad192_fin
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
  # Sin búfer: escribiendo a un fichero, Python acumula la salida y el registro
  # no enseñaba nada hasta el final (pasó con el primer juez).
  NLP_BACKEND=local PYTHONUNBUFFERED=1 .venv/bin/python spikes/fidelidad.py "$@" < /dev/null
  pkill -f "ssh -f -N .*-L $PUERTO:127.0.0.1:11434" && echo "túnel cerrado"
else
  echo "LA SESIÓN NO SE ABRIÓ: no se mide nada."
fi

# --- Cerrar la sesión y comprobar la GPU -------------------------------------------
ssh -n -o BatchMode=yes "$MAQUINA_2" 'touch /tmp/fidelidad192_fin'
wait "$LADO_2"
sed -n '/== máquina 2, al cerrar/,$p' "$REGISTRO/maquina2.log"
