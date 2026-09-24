#!/usr/bin/env bash
# Spike #181 (2026-09-24) - ¿Por dónde puede llegar la API a la A40?
#
# La API vive en la máquina 1 y Ollama en la máquina 2. §12 de
# `docs/arquitectura.md` dejaba dos caminos sin medir: un túnel SSH o un puerto
# abierto en la red de la universidad. Este guion mira qué deja pasar la red, en
# los dos sentidos y por las dos direcciones de cada máquina (la pública y la
# privada), antes de decidir nada.
#
# SÓLO LEE. No arranca servicios, no escribe ficheros y no toca la GPU. Para que
# un puerto «rechazado» signifique algo, en ninguno de los sondeados debe haber
# nadie escuchando: el guion no lo arregla, lo dice.
#
# Cada sondeo abre una conexión TCP con 3 s de plazo y distingue tres casos:
#   abierto        conecta: hay alguien escuchando;
#   rechazado      el paquete LLEGA y la máquina contesta que no hay nadie;
#   sin-respuesta  algo lo descarta por el camino, en la red o en la máquina.
# «Rechazado» y «sin-respuesta» no son lo mismo: el primero dice que abrir ese
# puerto bastaría; el segundo, que además habría que tocar un filtro.
#
# Ejecutar desde WSL:  bash spikes/red_entre_maquinas.sh
#
# A la máquina 2 se entra POR NOMBRE y con `BatchMode`: en `known_hosts` está
# por nombre, y por IP SSH se queda esperando a que se confirme la huella, sin
# ningún error.
exec 2>&1
MAQUINA_1=vmuser@193.147.60.40
MAQUINA_2=gongarcia@gserver2.tfg.etsii.urjc.es
PUBLICA_1=193.147.60.40
PUBLICA_2=193.147.60.32
PRIVADA_1=192.168.116.96
PRIVADA_2=192.168.116.87

read -r -d '' SONDEO <<'FUNCIONES'
sondear() {
  local inicio fin codigo estado
  inicio=$(date +%s%N)
  timeout 3 bash -c "</dev/tcp/$1/$2" 2>/dev/null
  codigo=$?
  fin=$(date +%s%N)
  case $codigo in
    0) estado=abierto ;;
    1) estado=rechazado ;;
    124) estado=sin-respuesta ;;
    *) estado="código-$codigo" ;;
  esac
  printf "  %-16s %-6s %-14s %s ms\n" "$1" "$2" "$estado" "$(awk "BEGIN{printf \"%.1f\", ($fin-$inicio)/1e6}")"
}
ida_y_vuelta() {
  ping -c 5 -W 2 "$1" < /dev/null | awk -F'/' '/^rtt/ {printf "  ping %s: %s ms de media\n", "'"$1"'", $5}'
}
FUNCIONES

remoto() {
  ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$1" 'bash -s'
}

echo "== condiciones"
echo "fecha: $(date -Is)"

echo "== desde WSL (fuera de la universidad) hacia la máquina 2"
eval "$SONDEO"
for puerto in 22 11434 11435; do sondear "$PUBLICA_2" "$puerto"; done

echo "== desde la máquina 1"
{
  echo "$SONDEO"
  cat <<EOF
echo "  máquina: \$(hostname) · \$(ip -4 -o addr show dev ens3 | awk '{print \$4}')"
echo "  dns: \$(getent hosts gserver2.tfg.etsii.urjc.es)"
echo "  claves propias para salir por SSH: \$(ls ~/.ssh/id_* 2>/dev/null | wc -l)"
ida_y_vuelta $PUBLICA_2
ida_y_vuelta $PRIVADA_2
for destino in $PUBLICA_2 $PRIVADA_2; do
  for puerto in 22 11434 11435; do sondear "\$destino" "\$puerto"; done
done
EOF
} | remoto "$MAQUINA_1"

echo "== desde la máquina 2"
{
  echo "$SONDEO"
  cat <<EOF
echo "  máquina: \$(hostname) · \$(ip -4 -o addr show dev ens3 | awk '{print \$4}')"
echo "  escuchando en 11434 o 11435: \$(ss -ltnH | awk '\$4 ~ /:1143[45]\$/' | wc -l)"
ida_y_vuelta $PRIVADA_1
for destino in $PUBLICA_1 $PRIVADA_1; do
  for puerto in 22 443 8000 11435; do sondear "\$destino" "\$puerto"; done
done
EOF
} | remoto "$MAQUINA_2"
