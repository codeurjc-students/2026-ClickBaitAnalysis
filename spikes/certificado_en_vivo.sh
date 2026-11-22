#!/usr/bin/env bash
# #213 (2026-11-10) - El certificado del sitio, desde fuera y en la máquina 1.
#
# Desde el 10 nov 2026 la máquina 1 sirve un certificado de HARICA emitido a
# mano, que no se renueva solo (`despliegue/README.md`, «El certificado»). Esto
# es lo que se comprueba después de instalarlo o de renovarlo, sin cambiar nada:
#
# - desde fuera: el certificado servido —sujeto, emisor, fechas y cadena—, si
#   `openssl` lo verifica y cuántos días le quedan; `curl` SIN `-k` contra `/`,
#   `/api/health` y `/api/agent`, desde WSL y, si está, con el `curl.exe` de
#   Windows, que usa otro almacén de confianza; y la redirección de `http://`;
# - en la máquina 1, por SSH y sólo leyendo: los permisos y el dueño de los dos
#   ficheros, cuántos certificados trae el `.pem`, que la clave casa con el
#   certificado (por el hash de la clave PÚBLICA: la privada no se imprime ni
#   sale de la máquina), el commit que sirve el clon, la versión de Caddy y la
#   salud de los tres servicios.
#
# Lo que no cuadra sale con «FALLA:», y al final, cuántas cosas fallan.
#
# Desde la raíz del repositorio, en WSL:
#   bash spikes/certificado_en_vivo.sh
exec 2>&1
cd "$(dirname "$0")/.." || exit 1
SITIO=gongarcia.tfg.etsii.urjc.es
MAQUINA_1=vmuser@193.147.60.40
AVISO_DIAS=30 # con menos días por delante, se da por fallo: hay que renovarlo
SALIDA=$(mktemp)
trap 'rm -f "$SALIDA"' EXIT

comprobar() {
  echo "== condiciones"
  echo "fecha: $(date -Is) · $(openssl version | cut -d' ' -f1-2) · $(curl --version | head -1 | cut -d' ' -f1-2) · guion: $(sha256sum spikes/certificado_en_vivo.sh | cut -c1-12)"

  echo "== el certificado servido"
  local servido fin dias
  servido=$(openssl s_client -connect "$SITIO:443" -servername "$SITIO" < /dev/null 2> /dev/null)
  echo "$servido" | openssl x509 -noout -subject -issuer -startdate -enddate | sed 's/^/  /'
  echo "  la cadena:"
  echo "$servido" | grep -E '^ *[0-9]+ s:|^ +i:' | sed 's/^/   /'
  if echo "$servido" | grep -q 'Verify return code: 0 (ok)'; then
    echo "  openssl lo verifica: Verify return code: 0 (ok)"
  else
    echo "  FALLA: openssl no lo verifica: $(echo "$servido" | grep -m1 'Verify return code')"
  fi
  fin=$(echo "$servido" | openssl x509 -noout -enddate | cut -d= -f2)
  dias=$((($(date -d "$fin" +%s) - $(date +%s)) / 86400))
  if [ "$dias" -ge "$AVISO_DIAS" ]; then
    echo "  le quedan $dias días"
  else
    echo "  FALLA: le quedan $dias días: hay que renovarlo (despliegue/README.md)"
  fi

  echo "== desde fuera, sin -k"
  local ruta resultado
  for ruta in / /api/health /api/agent; do
    resultado=$(curl -sS -o /dev/null --max-time 30 -w '%{http_code} · ssl_verify_result %{ssl_verify_result}' "https://$SITIO$ruta")
    if [ "$resultado" = "200 · ssl_verify_result 0" ]; then
      echo "  https://$SITIO$ruta -> $resultado"
    else
      echo "  FALLA: https://$SITIO$ruta -> $resultado"
    fi
  done
  if command -v curl.exe > /dev/null; then
    resultado=$(curl.exe -sS -o NUL --max-time 30 -w '%{http_code}' "https://$SITIO/" < /dev/null)
    if [ "$resultado" = 200 ]; then
      echo "  con el curl.exe de Windows: $resultado"
    else
      echo "  FALLA: con el curl.exe de Windows: $resultado"
    fi
  fi
  resultado=$(curl -sS -o /dev/null --max-time 15 -w '%{http_code} %{redirect_url}' "http://$SITIO/")
  if [ "$resultado" = "308 https://$SITIO/" ]; then
    echo "  http://$SITIO/ -> $resultado"
  else
    echo "  FALLA: http://$SITIO/ -> $resultado"
  fi

  echo "== en la máquina 1, sólo leyendo"
  cat << 'REMOTO' | ssh -T -o BatchMode=yes -o ConnectTimeout=10 "$MAQUINA_1" 'bash -s'
leer() {
  sudo stat -c '  %a %U:%G %n' /etc/clickbait/tls/certificado.pem /etc/clickbait/tls/clave.pem
  echo "  certificados en el .pem: $(sudo grep -c 'BEGIN CERTIFICATE' /etc/clickbait/tls/certificado.pem)"
  echo "  el autofirmado, en /etc/clickbait/tls.autofirmado: $(sudo ls /etc/clickbait/tls.autofirmado 2> /dev/null | tr '\n' ' ')"
  local del_certificado de_la_clave
  del_certificado=$(sudo openssl x509 -noout -pubkey -in /etc/clickbait/tls/certificado.pem | sha256sum | cut -c1-12)
  de_la_clave=$(sudo openssl pkey -pubout -in /etc/clickbait/tls/clave.pem | sha256sum | cut -c1-12)
  if [ "$del_certificado" = "$de_la_clave" ]; then
    echo "  la clave casa con el certificado (clave pública $del_certificado)"
  else
    echo "  FALLA: la clave no casa con el certificado ($del_certificado frente a $de_la_clave)"
  fi
  cd ~/2026-ClickBaitAnalysis || return
  echo "  el clon sirve $(git rev-parse --short HEAD), en $(git branch --show-current)"
  echo "  caddy $(sudo docker compose exec -T web caddy version < /dev/null | cut -d' ' -f1)"
  echo "  servicios: $(sudo docker compose ps --format '{{.Service}} {{.Health}}' < /dev/null | tr '\n' ' ')"
}
leer < /dev/null
REMOTO
}

comprobar 2>&1 | tee "$SALIDA"
echo "== cosas que no cuadran: $(grep -c 'FALLA:' "$SALIDA")"
