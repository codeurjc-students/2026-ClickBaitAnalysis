#!/usr/bin/env bash
# Spike #181 (2026-09-25) - ¿El túnel hace lo que debe, y SÓLO eso?
#
# La máquina 2 abre `ssh -R` hacia la 1 como el usuario `tunel`, que existe
# sólo para esto (ver `despliegue/maquina1/70-tunel.conf`). Este guion prueba
# las dos mitades:
#
#   lo permitido   escuchar en 172.17.0.1:11434 de la máquina 1, y que desde
#                  ahí lleguen el propio host y un contenedor de la red del
#                  compose, que es donde vive la API;
#   lo prohibido   una shell, escuchar en cualquier otra dirección o puerto, y
#                  el reenvío local (`-L`), que abriría conexiones DESDE la
#                  máquina 1 hacia donde quisiera quien tenga la clave.
#
# No usa la GPU ni Ollama: en la máquina 2 levanta un servidor HTTP de prueba
# en 127.0.0.1:18080 que contesta «contesta la máquina 2», y el túnel apunta a
# él. Al terminar, un `trap` lo cierra todo y el guion comprueba que no queda
# nada escuchando en ninguna de las dos máquinas.
#
# Ejecutar desde WSL:  bash spikes/tunel_restricciones.sh
exec 2>&1
MAQUINA_1=vmuser@193.147.60.40
MAQUINA_2=gongarcia@gserver2.tfg.etsii.urjc.es
SEGUNDOS_ABIERTO=25

remoto() {
  ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$1" 'bash -s'
}

echo "== condiciones"
echo "fecha: $(date -Is)"

# --- Máquina 2: lo prohibido, y después el túnel permitido abierto un rato ---
cat > /tmp/tunel_maquina2.sh <<REMOTO
SEGUNDOS_ABIERTO=$SEGUNDOS_ABIERTO
REMOTO
cat >> /tmp/tunel_maquina2.sh <<'REMOTO'
CLAVE="$HOME/.ssh/tunel_ollama"
DESTINO=tunel@192.168.116.96
OPCIONES=(-i "$CLAVE" -o BatchMode=yes -o ConnectTimeout=10 -o ExitOnForwardFailure=yes)
PROPIOS=""
limpiar() {
  for proceso in $PROPIOS; do kill "$proceso" 2>/dev/null; done
  rm -rf /tmp/tunel_prueba
}
trap limpiar EXIT INT TERM HUP

probar() {
  echo "== máquina 2: $(hostname) · $(ssh -V 2>&1)"
  mkdir -p /tmp/tunel_prueba
  echo "contesta la máquina 2" > /tmp/tunel_prueba/index.html
  python3 -m http.server 18080 --bind 127.0.0.1 --directory /tmp/tunel_prueba > /dev/null 2>&1 &
  PROPIOS="$PROPIOS $!"
  sleep 1

  echo "== lo prohibido"
  salida=$(timeout 15 ssh "${OPCIONES[@]}" "$DESTINO" true 2>&1); codigo=$?
  echo "  shell: código $codigo · «$(echo "$salida" | tail -1)»"

  for escucha in 172.17.0.1:11435 127.0.0.1:11434 0.0.0.0:11434 172.18.0.1:11434; do
    salida=$(timeout 15 ssh "${OPCIONES[@]}" -N -R "$escucha:127.0.0.1:18080" "$DESTINO" 2>&1); codigo=$?
    echo "  -R en $escucha: código $codigo · «$(echo "$salida" | grep -iE 'fail|denied|prohibit' | tail -1)»"
  done

  # -L: el túnel se establece, y lo que se rechaza es abrir el canal. Se intenta
  # llegar al propio sshd de la máquina 1: si pasara, llegaría su saludo.
  ssh "${OPCIONES[@]}" -N -L 127.0.0.1:18081:127.0.0.1:22 "$DESTINO" 2> /tmp/tunel_prueba/l.err &
  PROPIOS="$PROPIOS $!"
  sleep 3
  saludo=$(timeout 5 bash -c 'exec 3<>/dev/tcp/127.0.0.1/18081; head -c 20 <&3' 2>/dev/null)
  echo "  -L hacia el 22 de la máquina 1: «${saludo:-(nada)}» · ssh: «$(grep -iE 'prohibit|fail' /tmp/tunel_prueba/l.err | tail -1)»"

  echo "== lo permitido: -R 172.17.0.1:11434, abierto ${SEGUNDOS_ABIERTO} s"
  ssh "${OPCIONES[@]}" -o ServerAliveInterval=30 -N -R 172.17.0.1:11434:127.0.0.1:18080 "$DESTINO" &
  TUNEL=$!
  PROPIOS="$PROPIOS $TUNEL"
  sleep 3
  kill -0 "$TUNEL" 2>/dev/null && echo "  túnel abierto (pid $TUNEL)" || echo "  EL TÚNEL NO SE ABRIÓ"
  sleep "$SEGUNDOS_ABIERTO"
}
probar < /dev/null
limpiar
echo "== máquina 2, al terminar"
echo "  procesos propios: $(pgrep -u gongarcia -af 'tunel_ollama|http.server 18080' | grep -v pgrep | wc -l) · puerto 18080: $(ss -ltnH | awk '$4 ~ /:18080$/' | wc -l)"
REMOTO

remoto "$MAQUINA_2" < /tmp/tunel_maquina2.sh > /tmp/tunel_maquina2.log &
LADO_2=$!

# --- Máquina 1: mientras el túnel permitido está abierto ---
until grep -q "túnel abierto\|NO SE ABRIÓ" /tmp/tunel_maquina2.log 2>/dev/null; do
  kill -0 "$LADO_2" 2>/dev/null || break
  sleep 1
done

remoto "$MAQUINA_1" <<'M1' > /tmp/tunel_maquina1.log
probar() {
  echo "== máquina 1, con el túnel abierto"
  sudo ss -ltn | awk '$4 ~ /:1143[45]$/ {print "  escucha: " $4}'
  echo "  desde el host, 172.17.0.1:11434: «$(curl -s --max-time 3 http://172.17.0.1:11434/)»"
  cat > /tmp/sonda_tunel.py <<'PY'
import urllib.request
for nombre in ["host.docker.internal", "172.17.0.1"]:
    try:
        with urllib.request.urlopen(f"http://{nombre}:11434/", timeout=3) as respuesta:
            resultado = respuesta.read().decode().strip()
    except Exception as error:
        resultado = f"{type(error).__name__}: {getattr(error, 'reason', error)}"
    print(f"  desde un contenedor, {nombre}: «{resultado}»")
PY
  sudo docker run --rm --network clickbait_default \
    --add-host host.docker.internal:host-gateway \
    -v /tmp/sonda_tunel.py:/sonda.py:ro \
    --entrypoint python clickbait-backend /sonda.py
  rm -f /tmp/sonda_tunel.py
}
probar < /dev/null
M1

wait "$LADO_2"
cat /tmp/tunel_maquina2.log /tmp/tunel_maquina1.log

remoto "$MAQUINA_1" <<'M1'
echo "== máquina 1, al terminar"
echo "  escuchando en 11434/11435: $(sudo ss -ltnH | awk '$4 ~ /:1143[45]$/' | wc -l) · sesiones de tunel: $(pgrep -u tunel -c sshd)"
M1
rm -f /tmp/tunel_maquina2.sh /tmp/tunel_maquina2.log /tmp/tunel_maquina1.log
