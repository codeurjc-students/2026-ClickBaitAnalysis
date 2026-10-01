#!/usr/bin/env bash
# Spike #181 (2026-09-24) - ¿Qué puerto del host alcanza el contenedor de la API?
#
# El túnel hasta Ollama lo abre la máquina 2 con `ssh -R`, así que termina en la
# máquina 1 como un puerto que escucha EN EL HOST. Quien tiene que llegar a él
# es la API, que corre en un contenedor de la red `clickbait_default`, y para un
# contenedor `127.0.0.1` es él mismo. Con `gatewayports no` —lo que tiene el
# `sshd` de la máquina 1—, un `ssh -R` escucha sólo en el `127.0.0.1` del host.
#
# Se prueba sin túnel y sin ninguna clave: tres escuchas falsas en el 11434 del
# host, cada una en una dirección y contestando cuál es, y un contenedor
# desechable con la imagen del backend, en la red del compose, que intenta
# llegar a cada una:
#   127.0.0.1    lo que dejaría un `ssh -R` con la configuración actual;
#   172.17.0.1   la puerta de enlace de la red por defecto de Docker, que es a
#                donde resuelve `host.docker.internal` con `host-gateway`;
#   172.18.0.1   la de la red del compose, que depende del orden en que se
#                crean las redes.
#
# No toca los servicios desplegados. Al terminar, un `trap` mata las escuchas
# y borra los ficheros temporales, y el guion comprueba que no queda nadie en
# el 11434 ni ningún contenedor de más.
#
# Ejecutar desde WSL:  bash spikes/contenedor_a_host.sh
exec 2>&1
MAQUINA_1=vmuser@193.147.60.40

cat <<'REMOTO' | ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$MAQUINA_1" 'bash -s'
ESCUCHAS=""
limpiar() {
  for proceso in $ESCUCHAS; do kill "$proceso" 2>/dev/null; done
  ESCUCHAS=""
  rm -f /tmp/escucha_181.py /tmp/sonda_181.py
}
trap limpiar EXIT INT TERM HUP

probar() {
  echo "== condiciones"
  echo "fecha: $(date -Is)"
  echo "máquina: $(hostname) · docker $(sudo docker version --format '{{.Server.Version}}')"
  sudo docker network inspect bridge clickbait_default \
    --format '{{.Name}}: {{range .IPAM.Config}}{{.Subnet}}, puerta de enlace {{.Gateway}}{{end}}'
  echo "sshd: $(sudo sshd -T | grep -i '^gatewayports ')"
  if sudo ss -ltn | awk '$4 ~ /:11434$/' | grep -q .; then
    echo "ABORTADO: ya hay alguien escuchando en el 11434"
    return 1
  fi

  cat > /tmp/escucha_181.py <<'PY'
import http.server, sys
direccion = sys.argv[1]
class Responder(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        cuerpo = f"contesta la escucha de {direccion}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)
    def log_message(self, *argumentos):
        pass
http.server.HTTPServer((direccion, 11434), Responder).serve_forever()
PY
  cat > /tmp/sonda_181.py <<'PY'
import socket, urllib.request
for nombre in ["127.0.0.1", "host.docker.internal", "172.17.0.1", "172.18.0.1"]:
    try:
        direccion = socket.gethostbyname(nombre)
    except OSError as error:
        direccion = f"no resuelve ({error})"
    try:
        with urllib.request.urlopen(f"http://{nombre}:11434/", timeout=3) as respuesta:
            resultado = respuesta.read().decode()
    except Exception as error:
        resultado = f"{type(error).__name__}: {getattr(error, 'reason', error)}"
    print(f"  {nombre:22} -> {direccion:12} {resultado}")
PY

  for direccion in 127.0.0.1 172.17.0.1 172.18.0.1; do
    python3 /tmp/escucha_181.py "$direccion" &
    ESCUCHAS="$ESCUCHAS $!"
  done
  sleep 1
  echo "== escuchas en el host"
  sudo ss -ltn | awk '$4 ~ /:11434$/ {print "  " $4}'
  echo "== desde el propio host, a 127.0.0.1:11434"
  echo "  $(curl -s --max-time 3 http://127.0.0.1:11434/)"
  echo "== desde un contenedor desechable en clickbait_default, con host-gateway"
  sudo docker run --rm --network clickbait_default \
    --add-host host.docker.internal:host-gateway \
    -v /tmp/sonda_181.py:/sonda.py:ro \
    --entrypoint python clickbait-backend /sonda.py
}
probar < /dev/null
limpiar
echo "== después de limpiar"
sudo ss -ltn | awk '$4 ~ /:11434$/' | grep . || echo "  nadie en el 11434"
echo "  contenedores con la imagen del backend: $(sudo docker ps -a --filter ancestor=clickbait-backend --format '{{.Names}}' | paste -sd' ')"
REMOTO
