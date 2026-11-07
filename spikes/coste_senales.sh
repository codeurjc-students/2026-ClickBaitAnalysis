#!/usr/bin/env bash
# #256 (2026-11-07) - El coste de cada señal, en la CPU de la máquina 1.
#
# Lanza `spikes/coste_senales.py` donde corre producción, sobre la imagen que ya
# está desplegada, y deja los datos en `spikes/coste_senales/`. Una fila por
# contenedor, para que cada una empiece en un proceso nuevo (#125), y `PASADAS`
# veces las diez, tres por defecto: en la prueba en seco, en el PC, una misma
# fila cambió hasta cuatro veces de una pasada a otra.
#
# No toca los servicios ni el clon: cada contenedor es desechable, sin red
# (`--network none`), y sólo monta una carpeta temporal, de lectura. Comprueba
# que la imagen es la que sirve la API, y al terminar borra la carpeta y enseña
# el estado de los servicios. Todo va por UNA conexión SSH: la carpeta llega por
# la entrada de `ssh`, y lo que corre allí viene dentro de ella.
#
# Antes de la primera fila y después de la última dice, con `mincore`, qué parte
# de los pesos está en la caché de disco, como `spikes/ciclo_ollama.sh`. Vaciarla
# en una máquina de producción no se hace, así que lo que aquí se llama «primera
# llamada» no es el arranque en frío de verdad: el guion dice cuál fue el caso.
#
# Ejecutar desde WSL, en la raíz del repositorio. Se niega a pisar los datos de
# ese día. `COSTE_PYTHON`, para un worktree, que no tiene `.venv`:
#   setsid nohup bash spikes/coste_senales.sh > /tmp/coste_senales.log 2>&1 < /dev/null & disown
exec 2>&1
set -o pipefail
MAQUINA_1=vmuser@193.147.60.40
PASADAS=${1:-3}
PYTHON=${COSTE_PYTHON:-.venv/bin/python}
CARPETA=spikes/coste_senales
DATOS=$CARPETA/$(date +%F)-maquina1.jsonl
REGISTRO=$CARPETA/$(date +%F)-maquina1.log
TEMPORAL=/tmp/clickbait-coste-$$
LOCAL=$(mktemp -d)
trap 'rm -rf "$LOCAL"' EXIT

if [ -e "$DATOS" ]; then
  echo "ABORTADO: $DATOS ya existe."
  exit 1
fi
mkdir -p "$CARPETA"

FILAS=$("$PYTHON" spikes/coste_senales.py filas) || exit 1
"$PYTHON" spikes/coste_senales.py muestra "$LOCAL/muestra.json" || exit 1
cp spikes/coste_senales.py "$LOCAL/"

cat > "$LOCAL/cache_de_disco.py" <<'PY'
"""Qué parte de los pesos horneados está en la caché de disco (`mincore`)."""

import ctypes
import os
from pathlib import Path

from huggingface_hub.constants import HF_HUB_CACHE

UN_PESO = 10 * 1024 * 1024  # lo que pesa menos no son pesos
PAGINA = os.sysconf("SC_PAGE_SIZE")
LIBC = ctypes.CDLL("libc.so.6", use_errno=True)
LIBC.mmap.restype = ctypes.c_void_p
LIBC.mmap.argtypes = [
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_long,
]
LIBC.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]


def en_cache(ruta: Path, tamano: int) -> int:
    """Cuántas páginas del fichero están en memoria, sin leerlo."""
    descriptor = os.open(ruta, os.O_RDONLY)
    direccion = LIBC.mmap(None, tamano, 1, 1, descriptor, 0)  # sólo lectura, compartido
    paginas = (tamano + PAGINA - 1) // PAGINA
    vector = (ctypes.c_ubyte * paginas)()
    LIBC.mincore(direccion, tamano, vector)
    os.close(descriptor)
    return sum(byte & 1 for byte in vector)


for carpeta in sorted(Path(HF_HUB_CACHE).glob("models--*")):
    for blob in sorted((carpeta / "blobs").iterdir()):
        tamano = blob.stat().st_size
        if tamano < UN_PESO:
            continue
        paginas = (tamano + PAGINA - 1) // PAGINA
        porcentaje = 100 * en_cache(blob, tamano) / paginas
        print(f"  {carpeta.name}: {porcentaje:.1f} % de {tamano // 1024 // 1024} MiB")
PY

cat > "$LOCAL/remoto.sh" <<'REMOTO'
TEMPORAL=$1
PASADAS=$2
FILAS=$3

en_contenedor() {
  sudo docker run --rm --network none \
    -v "$TEMPORAL":/medida:ro \
    -e PYTHONPATH=/app -e NLP_BACKEND=local -e TQDM_DISABLE=1 \
    --entrypoint python clickbait-backend "$@" < /dev/null
}

cd ~/2026-ClickBaitAnalysis || exit 1
IMAGEN=$(sudo docker image inspect --format '{{.Id}}' clickbait-backend < /dev/null)
SERVIDA=$(sudo docker inspect --format '{{.Image}}' "$(sudo docker compose ps -q api < /dev/null)" < /dev/null)
echo "== condiciones"
echo "fecha: $(date -Is) · clon: $(git rev-parse --abbrev-ref HEAD) $(git rev-parse --short HEAD) · sin commitear: $(git status --porcelain | wc -l)"
echo "imagen: $IMAGEN"
echo "la que sirve la API: $SERVIDA"
if [ "$IMAGEN" != "$SERVIDA" ]; then
  echo "ABORTADO: la imagen no es la que está sirviendo la API."
  exit 1
fi
echo "docker: $(sudo docker version --format '{{.Server.Version}}' < /dev/null) · sistema: $(. /etc/os-release; echo "$PRETTY_NAME") · $(nproc) núcleos"
free -m | sed -n '1,2p'

echo "== la caché de disco, antes"
en_contenedor /medida/cache_de_disco.py || exit 1

for pasada in $(seq 1 "$PASADAS"); do
  for fila in $FILAS; do
    echo "== pasada $pasada · $fila · $(date +%T) · carga $(cut -d' ' -f1 /proc/loadavg)"
    if ! en_contenedor /medida/coste_senales.py medir "$fila" /medida/muestra.json; then
      echo "ABORTADO: ha fallado $fila."
      exit 1
    fi
  done
done

echo "== la caché de disco, después"
en_contenedor /medida/cache_de_disco.py
echo "== al terminar: $(date -Is)"
sudo docker compose ps --format '{{.Service}}: {{.State}} · {{.Status}}' < /dev/null
free -m | sed -n '1,2p'
REMOTO

tar czf - -C "$LOCAL" . \
  | ssh -o BatchMode=yes -o ConnectTimeout=10 "$MAQUINA_1" \
      "mkdir -p $TEMPORAL && tar xzf - -C $TEMPORAL && bash $TEMPORAL/remoto.sh $TEMPORAL $PASADAS '$FILAS'; salida=\$?; rm -rf $TEMPORAL; exit \$salida" \
  | tee "$REGISTRO"
SALIDA=$?

grep '^COSTE ' "$REGISTRO" | sed 's/^COSTE //' > "$DATOS"
ESPERADAS=$((PASADAS * $(echo "$FILAS" | wc -w)))
MEDIDAS=$(wc -l < "$DATOS")
echo
echo "== $MEDIDAS filas de $ESPERADAS, en $DATOS (salida de la sesión: $SALIDA)"
if [ "$SALIDA" -ne 0 ] || [ "$MEDIDAS" -ne "$ESPERADAS" ]; then
  echo "NO SE COMPLETÓ: los datos se quedan para mirarlos, y no valen como medida."
  exit 1
fi
"$PYTHON" spikes/coste_senales.py resumen "$DATOS"
