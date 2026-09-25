#!/usr/bin/env bash
# Spike #181 (2026-09-25) - ¿Cuánto añade el túnel a una petición a Ollama?
#
# El agente vivirá en la API, en la máquina 1, y hablará con Ollama, en la 2, por
# el túnel inverso que abre `gpu-sesion` (despliegue/). Este guion abre una
# sesión REAL —el 27B cargado en la A40— y mide lo mismo desde tres sitios:
#
#   máquina 2, sin túnel        la referencia: Ollama en local
#   máquina 1, host             por el túnel, en 172.17.0.1:11434
#   máquina 1, contenedor       por el túnel, como lo verá la API:
#                               `host.docker.internal` en la red del compose
#
# En cada uno, el MISMO medidor en Python: 20 `GET /api/version` y 10 respuestas
# cortas con el modelo ya cargado (`num_ctx` 8192, como el agente). De cada
# respuesta se resta el `total_duration` que da Ollama, así que «fuera de
# Ollama» es lo que se va en la red y en el túnel. Cada petición abre su propia
# conexión: es el caso sin reutilización, el peor para el túnel.
#
# Cerrada la sesión, mide además cuánto tarda la máquina 1 en saber que NO hay
# agente: lo que necesitará la interfaz para no ofrecer el chat (R6.14).
#
# Usa la GPU, con las normas de la máquina 2: `gpu-sesion` no abre si hay
# alguien en ella, la sesión dura como mucho 15 min, y al final se comprueba que
# la GPU vuelve a 0 MiB.
#
# Ejecutar desde WSL, con `gpu-sesion` instalado en la máquina 2:
#   bash spikes/latencia_tunel.sh
exec 2>&1
MAQUINA_1=vmuser@193.147.60.40
MAQUINA_2=gongarcia@gserver2.tfg.etsii.urjc.es
REGISTRO=$(mktemp -d)
trap 'rm -rf "$REGISTRO"' EXIT

remoto() {
  ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$1" 'bash -s'
}

read -r -d '' MEDIDOR <<'PY'
import json, statistics, sys, time, urllib.request

base, lugar = sys.argv[1], sys.argv[2]


def pedir(ruta, cuerpo=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(
        base + ruta, data=datos, headers={"Content-Type": "application/json"}
    )
    inicio = time.perf_counter()
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:
        contenido = respuesta.read()
    return time.perf_counter() - inicio, json.loads(contenido)


def resumir(nombre, segundos):
    ordenados = sorted(segundos)
    p90 = ordenados[int(0.9 * (len(ordenados) - 1))]
    print(
        f"  {lugar:24} {nombre:24} n={len(ordenados):2} · "
        f"mediana {statistics.median(ordenados) * 1000:7.1f} ms · p90 {p90 * 1000:7.1f} ms"
    )


resumir("GET /api/version", [pedir("/api/version")[0] for _ in range(20)])

cuerpo = {
    "model": "qwen3.5:27b",
    "stream": False,
    "think": False,
    "keep_alive": "10m",
    "messages": [{"role": "user", "content": "Responde sólo: ok"}],
    "options": {"num_ctx": 8192, "num_predict": 4},
}
relojes, fuera = [], []
for _ in range(10):
    reloj, respuesta = pedir("/api/chat", cuerpo)
    relojes.append(reloj)
    fuera.append(reloj - respuesta["total_duration"] / 1e9)
resumir("POST /api/chat, reloj", relojes)
resumir("  fuera de Ollama", fuera)
PY

read -r -d '' AUSENCIA <<'PY'
import statistics, sys, time, urllib.request

base, lugar = sys.argv[1], sys.argv[2]
tiempos, resultados = [], set()
for _ in range(10):
    inicio = time.perf_counter()
    try:
        urllib.request.urlopen(base + "/api/version", timeout=5).read()
        resultados.add("RESPONDIÓ")
    except Exception as error:
        resultados.add(type(getattr(error, "reason", error)).__name__)
    tiempos.append(time.perf_counter() - inicio)
print(
    f"  {lugar:24} sin agente: mediana {statistics.median(tiempos) * 1000:.1f} ms"
    f" · máx {max(tiempos) * 1000:.1f} ms · {', '.join(sorted(resultados))}"
)
PY

instalar() { # $1 = nombre del fichero remoto, $2 = contenido
  echo "cat > /tmp/$1 <<'FIN_PY'"
  printf '%s\n' "$2"
  echo "FIN_PY"
}

echo "== condiciones"
echo "fecha: $(date -Is) · commit: $(git -C "$(dirname "$0")" rev-parse --short HEAD)"

# --- Máquina 2: la sesión, con la medida local dentro ---------------------------
{
  instalar latencia_medidor.py "$MEDIDOR"
  cat <<'REMOTO'
cat > /tmp/latencia_sesion.sh <<'SESION'
echo "== máquina 2: el modelo, cargado"
curl -s http://127.0.0.1:11434/api/chat -d '{"model":"qwen3.5:27b","stream":false,"think":false,"keep_alive":"10m","messages":[{"role":"user","content":"Responde sólo: ok"}],"options":{"num_ctx":8192,"num_predict":4}}' \
  | jq -r '"  carga: \(.load_duration/1e9) s · total: \(.total_duration/1e9) s"'
echo "== máquina 2, sin túnel"
python3 /tmp/latencia_medidor.py http://127.0.0.1:11434 "máquina 2, sin túnel"
echo "LISTO PARA LA MÁQUINA 1"
for _ in $(seq 1 240); do [ -f /tmp/latencia_fin ] && break; sleep 1; done
SESION
rm -f /tmp/latencia_fin
echo "máquina 2: $(hostname) · ollama $(~/.local/ollama/bin/ollama --version 2>&1 | grep -o '[0-9][0-9.]*' | tail -1) · qwen3.5:27b $(sha256sum ~/.ollama/models/manifests/registry.ollama.ai/library/qwen3.5/27b | cut -c1-12) · gpu-sesion $(sha256sum ~/bin/gpu-sesion | cut -c1-12)"
echo "gpu antes: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB · procesos: $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .)"
GPU_SESION_MAX=15m ~/bin/gpu-sesion bash /tmp/latencia_sesion.sh < /dev/null
sleep 2
echo "== máquina 2, al cerrar la sesión"
echo "  gpu: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB · procesos: $(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .) · ollama propios: $(pgrep -u gongarcia -c -x ollama) · túneles propios: $(pgrep -u gongarcia -cf '[t]unel_ollama')"
rm -f /tmp/latencia_medidor.py /tmp/latencia_sesion.sh /tmp/latencia_fin
REMOTO
} | remoto "$MAQUINA_2" > "$REGISTRO/maquina2.log" &
LADO_2=$!

until grep -q "LISTO PARA LA MÁQUINA 1" "$REGISTRO/maquina2.log" 2> /dev/null; do
  kill -0 "$LADO_2" 2> /dev/null || break
  sleep 2
done

# --- Máquina 1: por el túnel, con la sesión abierta ------------------------------
if grep -q "LISTO PARA LA MÁQUINA 1" "$REGISTRO/maquina2.log"; then
  {
    instalar latencia_medidor.py "$MEDIDOR"
    cat <<'M1'
medir() {
  echo "== máquina 1, por el túnel"
  python3 /tmp/latencia_medidor.py http://172.17.0.1:11434 "máquina 1, host"
  sudo docker run --rm --network clickbait_default \
    --add-host host.docker.internal:host-gateway \
    -v /tmp/latencia_medidor.py:/medidor.py:ro \
    --entrypoint python clickbait-backend /medidor.py \
    http://host.docker.internal:11434 "máquina 1, contenedor"
}
medir < /dev/null
M1
  } | remoto "$MAQUINA_1" > "$REGISTRO/maquina1.log"
fi

ssh -n -T -o BatchMode=yes "$MAQUINA_2" 'touch /tmp/latencia_fin'
wait "$LADO_2"

# --- Máquina 1: con la sesión cerrada ------------------------------------------
{
  instalar latencia_ausencia.py "$AUSENCIA"
  cat <<'M1'
comprobar() {
  echo "== máquina 1, con la sesión cerrada"
  python3 /tmp/latencia_ausencia.py http://172.17.0.1:11434 "máquina 1, host"
  sudo docker run --rm --network clickbait_default \
    --add-host host.docker.internal:host-gateway \
    -v /tmp/latencia_ausencia.py:/ausencia.py:ro \
    --entrypoint python clickbait-backend /ausencia.py \
    http://host.docker.internal:11434 "máquina 1, contenedor"
  echo "  escuchando en 11434: $(sudo ss -ltnH | awk '$4 ~ /:11434$/' | wc -l) · sesiones de tunel: $(pgrep -u tunel -c sshd)"
  rm -f /tmp/latencia_medidor.py /tmp/latencia_ausencia.py
}
comprobar < /dev/null
M1
} | remoto "$MAQUINA_1" > "$REGISTRO/ausencia.log"

cat "$REGISTRO/maquina2.log" "$REGISTRO/maquina1.log" "$REGISTRO/ausencia.log" 2> /dev/null
