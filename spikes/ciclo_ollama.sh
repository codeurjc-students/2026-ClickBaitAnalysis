#!/usr/bin/env bash
# Spike #181 (2026-09-24) - ¿Quién arranca Ollama, y cuándo suelta la GPU?
#
# La máquina 2 es compartida y la norma es no dejar la GPU bloqueada. Antes de
# decidir si Ollama se arranca bajo demanda o se queda arrancado, hay que saber
# qué ocupa en cada estado y cuánto cuesta llegar desde cero a una respuesta.
#
# Mide, con `qwen3.5:27b` y `num_ctx` 8192 (lo que usará el agente):
#   - la memoria de GPU con `ollama serve` y SIN modelo;
#   - la memoria con el modelo cargado, y cuándo se suelta al vencer el
#     `keep_alive` (15 s aquí);
#   - el tiempo desde cero: servidor listo, primera petición (carga incluida) y
#     una segunda con el modelo ya cargado;
#   - qué parte de los pesos estaba ya en la caché de disco, con `mincore`.
#     Sin sudo no se puede vaciar esa caché, así que el arranque en frío de
#     verdad queda sin medir: el guion dice cuál fue el caso.
#
# Dos modos, porque la A40 está en pass-through con el modo persistente
# DESACTIVADO, y cada vez que alguien abre la GPU el driver la vuelve a
# inicializar (~2 s; un `nvidia-smi` también los paga):
#
#   bash spikes/ciclo_ollama.sh                 # la máquina tal cual está
#   bash spikes/ciclo_ollama.sh --gpu-abierta   # con un `nvidia-smi -l 1`
#                                               # sosteniéndola abierta, que es
#                                               # lo que haría el modo
#                                               # persistente. No ocupa memoria.
#
# Se lanza DESDE WSL y corre en la máquina 2 por SSH. Normas de esa máquina: si
# hay alguien en la GPU NO arranca; el `trap` mata sólo los procesos propios,
# también si se corta la conexión; y al final se comprueba que la GPU vuelve a
# 0 MiB. El registro del servidor queda en `~/.ollama-medida-181.log` allí.
exec 2>&1
M2=gongarcia@gserver2.tfg.etsii.urjc.es
MODO=normal
[ "${1:-}" = "--gpu-abierta" ] && MODO=gpu-abierta

{ echo "MODO=$MODO"; cat <<'REMOTO'
SERVIDOR=""
SOSTEN=""
liberar() {
  for proceso in $SERVIDOR $SOSTEN; do
    kill "$proceso" 2>/dev/null && wait "$proceso" 2>/dev/null
  done
  SERVIDOR=""
  SOSTEN=""
}
trap liberar EXIT INT TERM HUP

medir() {
  set -u
  local OLLAMA="$HOME/.local/ollama/bin/ollama"
  local HOSTPORT="127.0.0.1:11434"
  local URL="http://$HOSTPORT"
  local MODELO="qwen3.5:27b"
  local KEEP_ALIVE="15s"
  local REGISTRO="$HOME/.ollama-medida-181.log"

  ahora() { date +%s%N; }
  segundos() { awk "BEGIN{printf \"%.2f\", ($2-$1)/1e9}"; }
  gpu_mib() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' '; }
  procesos_gpu() { nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader | paste -sd';' | sed 's/^$/ninguno/'; }
  propios() { pgrep -u gongarcia -a 'ollama|nvidia-smi' | awk '{print $1, $2, $3}' | paste -sd';' | sed 's/^$/ninguno/'; }
  abrir_gpu() {
    local inicio fin
    inicio=$(ahora); nvidia-smi --query-gpu=name --format=csv,noheader > /dev/null; fin=$(ahora)
    segundos "$inicio" "$fin"
  }

  echo "== condiciones"
  echo "fecha: $(date -Is) · modo: $MODO"
  echo "máquina: $(hostname)"
  nvidia-smi --query-gpu=name,driver_version,memory.total,persistence_mode --format=csv,noheader | sed 's/^/gpu: /'
  echo "ollama: $("$OLLAMA" --version 2>&1 | grep -o '[0-9][0-9.]*' | tail -1)"

  echo "== antes de arrancar"
  if [ "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c .)" -gt 0 ] || pgrep -x ollama >/dev/null; then
    echo "ABORTADO: hay procesos en la GPU o un Ollama de alguien: $(procesos_gpu)"
    return 1
  fi
  echo "gpu_mib: $(gpu_mib) · procesos: $(procesos_gpu)"

  # Qué parte de los pesos está ya en la caché de disco (mincore): sin esto no
  # se sabe si la carga fue en frío o en caliente.
  local manifiesto="$HOME/.ollama/models/manifests/registry.ollama.ai/library/qwen3.5/27b"
  local digest
  digest=$(jq -r '.layers[] | select(.mediaType=="application/vnd.ollama.image.model") | .digest' "$manifiesto")
  echo "pesos: ${digest:0:19}…"
  python3 - "$HOME/.ollama/models/blobs/${digest/:/-}" <<'PY'
import ctypes, os, sys
ruta = sys.argv[1]
tam = os.path.getsize(ruta)
pagina = os.sysconf("SC_PAGE_SIZE")
libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.mmap.restype = ctypes.c_void_p
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
descriptor = os.open(ruta, os.O_RDONLY)
direccion = libc.mmap(None, tam, 1, 1, descriptor, 0)  # PROT_READ, MAP_SHARED
paginas = (tam + pagina - 1) // pagina
vector = (ctypes.c_ubyte * paginas)()
libc.mincore(direccion, tam, vector)
residentes = len(bytes(vector).translate(None, bytes(range(0, 256, 2))))
print(f"pesos_en_cache: {100 * residentes / paginas:.1f} % de {tam / 2**30:.1f} GiB")
PY

  echo "abrir_gpu_s (nvidia-smi, sin nada abierto): $(abrir_gpu)"
  if [ "$MODO" = "gpu-abierta" ]; then
    nvidia-smi -l 1 > /dev/null &
    SOSTEN=$!
    sleep 3
    echo "abrir_gpu_s (con nvidia-smi -l 1 sosteniéndola): $(abrir_gpu)"
  fi

  echo "== arrancar el servidor"
  local t0 t1
  t0=$(ahora)
  OLLAMA_HOST="$HOSTPORT" "$OLLAMA" serve >"$REGISTRO" 2>&1 &
  SERVIDOR=$!
  until curl -sf "$URL/api/version" >/dev/null; do
    kill -0 "$SERVIDOR" 2>/dev/null || { echo "el servidor murió; registro:"; tail -5 "$REGISTRO"; return 1; }
    sleep 0.1
  done
  t1=$(ahora)
  echo "servidor_listo_s: $(segundos "$t0" "$t1")"

  echo "== servidor sin modelo"
  sleep 5
  echo "gpu_mib: $(gpu_mib) · procesos: $(procesos_gpu) · propios: $(propios)"

  echo "== primera petición: carga + primera respuesta"
  local cuerpo respuesta t2 t3
  cuerpo=$(jq -nc --arg m "$MODELO" --arg k "$KEEP_ALIVE" '{model:$m, keep_alive:$k, stream:false, think:false,
    messages:[{role:"user", content:"Responde sólo: ok"}], options:{num_ctx:8192, num_predict:16}}')
  t2=$(ahora)
  respuesta=$(curl -sf "$URL/api/chat" -d "$cuerpo")
  t3=$(ahora)
  echo "reloj_s: $(segundos "$t2" "$t3")"
  echo "$respuesta" | jq -r '"load_s: \(.load_duration/1e9) · prompt_eval: \(.prompt_eval_count) en \(.prompt_eval_duration/1e9) s · eval: \(.eval_count) en \(.eval_duration/1e9) s · total_s: \(.total_duration/1e9) · texto: \(.message.content|tostring|gsub("\n";" ")|.[0:40])"'
  echo "gpu_mib: $(gpu_mib) · procesos: $(procesos_gpu)"
  curl -sf "$URL/api/ps" | jq -r '.models[] | "cargado: \(.name) · size_vram_gib: \((.size_vram/1073741824*100|floor)/100) · context: \(.context_length // "?")"'

  echo "== segunda petición, con el modelo caliente"
  t2=$(ahora)
  respuesta=$(curl -sf "$URL/api/chat" -d "$cuerpo")
  t3=$(ahora)
  echo "reloj_s: $(segundos "$t2" "$t3")"
  echo "$respuesta" | jq -r '"load_s: \(.load_duration/1e9) · total_s: \(.total_duration/1e9)"'

  # Se sondea la API cada medio segundo y `nvidia-smi` sólo al final: cada
  # llamada a `nvidia-smi` cuesta ~2 s con el modo persistente desactivado, y
  # habría sido ésa la resolución de la medida.
  echo "== esperar a que venza el keep_alive ($KEEP_ALIVE)"
  local t4 descargado="" liberada=""
  for _ in $(seq 1 240); do
    sleep 0.5
    if [ "$(curl -sf "$URL/api/ps" | jq '.models | length')" = "0" ]; then
      t4=$(ahora); descargado=$(segundos "$t3" "$t4"); break
    fi
  done
  for _ in $(seq 1 30); do
    if [ "$(gpu_mib)" -le 1 ]; then t4=$(ahora); liberada=$(segundos "$t3" "$t4"); break; fi
  done
  echo "descargado_tras_s: ${descargado:-no en 120 s} · gpu_en_0_comprobada_tras_s: ${liberada:-no}"

  echo "== servidor sin modelo, después"
  sleep 5
  echo "gpu_mib: $(gpu_mib) · procesos: $(procesos_gpu) · propios: $(propios)"

  echo "== parar lo propio"
  liberar
  sleep 2
  echo "gpu_mib: $(gpu_mib) · procesos: $(procesos_gpu) · propios: $(propios)"
}
medir < /dev/null
REMOTO
} | ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$M2" 'bash -s'
echo "salida: $?"
