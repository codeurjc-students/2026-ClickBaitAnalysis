# Despliegue

Lo que se instala o se ejecuta **directamente en una máquina de despliegue**,
fuera de toda imagen. Aquí está el cómo; el porqué de cada decisión está en el
README principal, en la sección de #181.

| Fichero | Dónde se instala | Qué es |
|---|---|---|
| `maquina1/70-tunel.conf` | `/etc/ssh/sshd_config.d/` de la máquina 1 | Lo único que puede hacer el usuario `tunel`: escuchar en `172.17.0.1:11434` |
| `maquina2/gpu-sesion` | `~/bin/` de la máquina 2 | Levanta Ollama bajo demanda, abre el túnel y lo suelta todo al salir, con una duración máxima |

Las dos máquinas: la **1** es la de la aplicación (`gongarcia.tfg.etsii.urjc.es`,
con `sudo`) y la **2** la de la GPU (`gserver2.tfg.etsii.urjc.es`, compartida y
sin `sudo`).

## El túnel de Ollama

La API, en la máquina 1, llega a Ollama, en la 2, por un túnel SSH **inverso**:
lo abre la máquina 2 hacia la 1. La 2 sólo acepta conexiones por el 22, y así la
1, que está en internet, no guarda ninguna llave de la máquina compartida.

El túnel escucha en `172.17.0.1:11434` de la máquina 1, la puerta de enlace de la
red por defecto de Docker, porque es lo que alcanza el contenedor de la API
—como `host.docker.internal`—. El `127.0.0.1` del host, donde escucharía un
`ssh -R` sin más, no lo alcanza.

### 1 · Máquina 2: la clave del túnel

```bash
ssh-keygen -t ed25519 -f ~/.ssh/tunel_ollama -N "" -C "tunel-ollama@gserver2"
```

Sin frase de paso, porque la usa `gpu-sesion`. Lo que permite está acotado en la
máquina 1 (paso 2), en dos sitios.

### 2 · Máquina 1: el usuario `tunel` y lo que puede hacer

Desde el clon del repositorio (`~/2026-ClickBaitAnalysis`):

```bash
sudo useradd --system --user-group --create-home --home-dir /var/lib/tunel --shell /usr/sbin/nologin tunel
sudo usermod -p '*' tunel
sudo install -d -m 700 -o tunel -g tunel /var/lib/tunel/.ssh
echo 'restrict,port-forwarding,permitlisten="172.17.0.1:11434" <el contenido de ~/.ssh/tunel_ollama.pub de la máquina 2>' | sudo tee /var/lib/tunel/.ssh/authorized_keys > /dev/null
sudo chown tunel:tunel /var/lib/tunel/.ssh/authorized_keys && sudo chmod 600 /var/lib/tunel/.ssh/authorized_keys
sudo install -m 644 despliegue/maquina1/70-tunel.conf /etc/ssh/sshd_config.d/70-tunel.conf
```

`usermod -p '*'` deja la cuenta sin contraseña válida pero sin bloquear: una
cuenta bloqueada (`!`, lo que pone `useradd`) puede rechazar también las claves,
según PAM.

**Antes de recargar `sshd`**, comprobar la configuración que va a quedar:

```bash
sudo sshd -t
sudo sshd -T -C user=tunel,host=gserver2,addr=192.168.116.87 | grep -E '^(allowtcpforwarding|gatewayports|permitlisten|permitopen|forcecommand) '
sudo sshd -T -C user=vmuser,host=casa,addr=203.0.113.1 | grep -E '^(allowtcpforwarding|gatewayports|permitlisten) '
```

Para `tunel` tiene que salir `remote`, `clientspecified`, `172.17.0.1:11434`,
`none` y `/usr/sbin/nologin`; para `vmuser`, lo de siempre: `yes`, `no` y `any`.
Si `vmuser` cambia, el bloque `Match` se ha extendido a lo que viene detrás y
**no hay que recargar**. Después, **con otra sesión SSH abierta** por si acaso:

```bash
sudo systemctl reload ssh
```

### 3 · Máquina 2: la primera conexión

```bash
ssh -i ~/.ssh/tunel_ollama tunel@192.168.116.96
```

Por la red privada, que es la ruta directa. Pregunta por la huella de la máquina
1, que se contrasta en ella con `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`
(el 2026-09-25 era `SHA256:LobkHDR+sdDq/LsUe53GU4lpTG/vuimCpGLWcP2CdCM`). Tiene
que contestar «This account is currently not available» y cerrarse.

### 4 · La comprobación

Desde WSL, en la raíz del repositorio:

```bash
bash spikes/tunel_restricciones.sh
```

Prueba lo permitido —el túnel en `172.17.0.1:11434`, alcanzable desde el host y
desde un contenedor de la red del compose— y lo prohibido: una shell, escuchar en
cualquier otra dirección o puerto, y el reenvío local. No usa la GPU.

## `gpu-sesion`

Instalación, desde WSL:

```bash
scp despliegue/maquina2/gpu-sesion gongarcia@gserver2.tfg.etsii.urjc.es:bin/gpu-sesion
```

Uso, en la máquina 2:

```bash
gpu-sesion                        # una shell con Ollama y el túnel detrás
gpu-sesion <comando>              # ejecuta el comando y lo suelta todo al terminar
GPU_SESION_MAX=30m gpu-sesion     # duración máxima (defecto: 2h)
GPU_SESION_TUNEL=0 gpu-sesion     # sin túnel, sólo Ollama en local
```

No abre la sesión si hay otro proceso en la GPU (sin terminal, ni pregunta), si
ya hay un Ollama en el 11434, o si el túnel no se puede abrir. Al salir —por el
final del comando, por Ctrl-C, al cerrar la terminal o al agotar la duración
máxima— cierra primero el túnel y después Ollama.
