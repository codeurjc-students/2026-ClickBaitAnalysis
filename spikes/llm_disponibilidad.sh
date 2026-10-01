#!/usr/bin/env bash
# #187 (2026-09-25) - El cliente del modelo de lenguaje, contra la A40 de verdad.
#
# Los tests simulan Ollama. Esto ejecuta el código del commit actual —el
# `backend/` de la rama, no el de la imagen desplegada— en un contenedor
# desechable de la máquina 1, en la red del compose y con `host-gateway`, que es
# exactamente como lo verá la API. Y provoca los cuatro estados de
# disponibilidad (R6.14) de verdad:
#
#   sin configurar    `LLM_BACKEND` sin poner
#   apagado           configurado, sin sesión: la conexión por el túnel se
#                     RECHAZA, que es lo único que el cliente llama «apagado»
#   sin el modelo     sesión abierta y un modelo que el servidor no tiene
#   disponible        sesión abierta y el 27B, más un chat real con una
#                     herramienta, para ver que la llamada y las medidas se leen
#
# No toca los servicios desplegados ni el clon de la máquina 1: copia `backend/`
# a una carpeta temporal y la monta sobre la imagen. La sesión de la GPU la abre
# `gpu-sesion` con 10 min como máximo, y al terminar se comprueba que la GPU
# vuelve a 0 MiB.
#
# Ejecutar desde WSL, en la raíz del repositorio y con los cambios commiteados:
#   bash spikes/llm_disponibilidad.sh
exec 2>&1
MAQUINA_1=vmuser@193.147.60.40
MAQUINA_2=gongarcia@gserver2.tfg.etsii.urjc.es
TEMPORAL=/tmp/clickbait-llm-$$
REGISTRO=$(mktemp -d)
trap 'rm -rf "$REGISTRO"' EXIT

remoto() {
  ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$1" 'bash -s'
}

if ! git diff --quiet HEAD -- backend; then
  echo "ABORTADO: backend/ tiene cambios sin commitear; lo medido no sería el commit."
  exit 1
fi

echo "== condiciones"
echo "fecha: $(date -Is) · commit: $(git rev-parse --short HEAD) · rama: $(git branch --show-current)"

# El código de la rama, a la máquina 1.
tar czf - --exclude=__pycache__ backend \
  | ssh -o BatchMode=yes "$MAQUINA_1" "mkdir -p $TEMPORAL && tar xzf - -C $TEMPORAL"

read -r -d '' SONDA <<'PY'
import asyncio, sys, time

from backend.integrations.llm import factory

HERRAMIENTA = {
    "name": "detect_clickbait_lexical",
    "description": "Detecta clickbait por pistas léxicas y estructurales del titular, y devuelve qué pistas aparecen y dónde.",
    "parameters": {
        "type": "object",
        "properties": {"headline": {"type": "string", "description": "Titular a evaluar (en inglés)."}},
        "required": ["headline"],
    },
}


async def principal(caso):
    estado = await factory.disponibilidad()
    print(f"  {caso:14} {estado.status:14} modelo={estado.model} · «{estado.detail}»")
    if caso != "disponible" or estado.status != "available":
        return
    mensajes = [{
        "role": "user",
        "content": "¿Qué pistas léxicas tiene el titular 'You Won't Believe What Happened Next'?",
    }]
    inicio = time.perf_counter()
    resultado = await factory.get_llm_backend().chat(mensajes, [HERRAMIENTA])
    reloj = time.perf_counter() - inicio
    if not resultado.success:
        print(f"  chat: FALLO · «{resultado.error}»")
        return
    respuesta = resultado.unwrap()
    print(f"  chat: {reloj:.2f} s de reloj · llamadas={respuesta['tool_calls']}")
    print(f"        medidas={respuesta['metrics']} · texto={respuesta['content'][:80]!r}")


asyncio.run(principal(sys.argv[1]))
PY

sondear() { # $1 = caso, $2… = variables de entorno del modelo
  local caso=$1
  shift
  local variables=""
  for variable in "$@"; do variables="$variables -e $variable"; done
  cat <<EOF
sudo docker run --rm --network clickbait_default \
  --add-host host.docker.internal:host-gateway \
  -v $TEMPORAL/backend:/app/backend:ro -v $TEMPORAL/sonda.py:/sonda.py:ro \
  -e PYTHONPATH=/app -e GUARDIAN_API_KEY=x -e NYT_API_KEY=x -e HF_TOKEN=x $variables \
  --entrypoint python clickbait-backend /sonda.py $caso 2>&1
EOF
}

CONFIGURADO="LLM_BACKEND=ollama LLM_URL=http://host.docker.internal:11434"

# --- Máquina 1, sin sesión: los dos primeros estados -------------------------
{
  echo "cat > $TEMPORAL/sonda.py <<'FIN_PY'"
  printf '%s\n' "$SONDA"
  echo "FIN_PY"
  echo "comprobar() {"
  echo "echo '== máquina 1, sin sesión'"
  echo "echo \"  escuchando en 11434 antes de empezar: \$(sudo ss -ltnH | awk '\$4 ~ /:11434\$/' | wc -l)\""
  sondear sin_configurar
  # shellcheck disable=SC2086
  sondear apagado $CONFIGURADO
  echo "}"
  echo "comprobar < /dev/null"
} | remoto "$MAQUINA_1" > "$REGISTRO/sin_sesion.log"

# --- Máquina 2: la sesión, abierta hasta que la máquina 1 termine -------------
cat <<'M2' | remoto "$MAQUINA_2" > "$REGISTRO/maquina2.log" &
cat > /tmp/llm_sesion.sh <<'SESION'
echo "LISTO PARA LA MÁQUINA 1"
for _ in $(seq 1 300); do [ -f /tmp/llm_fin ] && break; sleep 1; done
SESION
rm -f /tmp/llm_fin
echo "máquina 2: ollama $(~/.local/ollama/bin/ollama --version 2>&1 | grep -o '[0-9][0-9.]*' | tail -1) · qwen3.5:27b $(sha256sum ~/.ollama/models/manifests/registry.ollama.ai/library/qwen3.5/27b | cut -c1-12) · gpu antes: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB"
GPU_SESION_MAX=10m ~/bin/gpu-sesion bash /tmp/llm_sesion.sh < /dev/null
sleep 2
echo "máquina 2, al cerrar: gpu $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB · procesos $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .) · ollama propios $(pgrep -u gongarcia -c -x ollama)"
rm -f /tmp/llm_sesion.sh /tmp/llm_fin
M2
LADO_2=$!

until grep -q "LISTO PARA LA MÁQUINA 1" "$REGISTRO/maquina2.log" 2> /dev/null; do
  kill -0 "$LADO_2" 2> /dev/null || break
  sleep 2
done

# --- Máquina 1, con la sesión abierta: los otros dos estados y un chat ---------
if grep -q "LISTO PARA LA MÁQUINA 1" "$REGISTRO/maquina2.log"; then
  {
    echo "comprobar() {"
    echo "echo '== máquina 1, con la sesión abierta'"
    # shellcheck disable=SC2086
    sondear sin_el_modelo $CONFIGURADO LLM_MODEL=qwen3.5:no-existe
    # shellcheck disable=SC2086
    sondear disponible $CONFIGURADO
    echo "}"
    echo "comprobar < /dev/null"
  } | remoto "$MAQUINA_1" > "$REGISTRO/con_sesion.log"
fi

ssh -n -T -o BatchMode=yes "$MAQUINA_2" 'touch /tmp/llm_fin'
wait "$LADO_2"
ssh -n -T -o BatchMode=yes "$MAQUINA_1" "rm -rf $TEMPORAL; echo \"== máquina 1, al terminar: carpeta temporal borrada · escuchando en 11434: \$(sudo ss -ltnH | awk '\$4 ~ /:11434\$/' | wc -l)\"" > "$REGISTRO/final.log"

cat "$REGISTRO/sin_sesion.log" "$REGISTRO/maquina2.log" "$REGISTRO/con_sesion.log" "$REGISTRO/final.log" 2> /dev/null
