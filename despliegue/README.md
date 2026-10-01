# Despliegue

Lo que se instala o se ejecuta **directamente en una máquina de despliegue**,
fuera de toda imagen, y cómo se opera el día a día. Aquí está el cómo; el porqué
de cada decisión está en el README principal, en las secciones de #164 (el
compose), #181 (el túnel y `gpu-sesion`) y #193 (este procedimiento).

| Fichero | Dónde se instala | Qué es |
|---|---|---|
| `maquina1/70-tunel.conf` | `/etc/ssh/sshd_config.d/` de la máquina 1 | Lo único que puede hacer el usuario `tunel`: escuchar en `172.17.0.1:11434` |
| `maquina2/gpu-sesion` | `~/bin/` de la máquina 2 | Levanta Ollama bajo demanda, abre el túnel y lo suelta todo al salir, con una duración máxima |

Las dos máquinas: la **1** es la de la aplicación (`gongarcia.tfg.etsii.urjc.es`,
con `sudo`) y la **2** la de la GPU (`gserver2.tfg.etsii.urjc.es`, compartida y
sin `sudo`).

## El día a día: desplegar, encender el asistente y apagarlo

La aplicación vive en la máquina 1 y funciona sola. El asistente necesita además
el modelo, que corre en la máquina 2 **sólo mientras alguien tiene abierta una
sesión de GPU**: es una máquina compartida, y la norma de su administrador es no
dejar la GPU ocupada. El orden importa:

1. **Primero la máquina 1**, si hay algo que desplegar: compilar no necesita la
   GPU, así que no se ocupa mientras tanto.
2. **Después, la sesión de GPU**, sólo mientras se vaya a usar el asistente.
3. **Al terminar, se cierra la sesión**, y se comprueba que la GPU queda libre.
   La máquina 1 se queda como está: sin sesión, la pantalla del asistente
   explica que está apagado, y el análisis sigue funcionando.

Los comandos van con el usuario y el nombre de cada máquina, no con alias. A la
máquina 2 se entra **por nombre**: por IP, SSH se queda esperando a que alguien
confirme la huella, sin dar error. Si SSH contesta «Host key verification
failed», esa copia de `known_hosts` conoce la máquina por su IP y no por su
nombre (pasa en WSL con la máquina 1): se entra una vez sin `BatchMode`, se
contrasta la huella y se acepta.

⚠️ **A la máquina 2 no se la sondea por SSH en bucle.** El 30 de septiembre, un
guion de prueba que se conectaba cada segundo para ver si la sesión había
terminado hizo que la máquina 2 empezara a cortar las conexiones, y después la
universidad bloqueó la IP de casa, también para la aplicación, que seguía
funcionando desde otra red. Para saber si el asistente está, se pregunta a la API
(`/api/agent`); a la máquina 2 se entra una vez para abrir la sesión y otra para
comprobar que se cerró.

### Máquina 1: desplegar

Antes de nada, en qué rama está el clon y si tiene cambios. Tiene que decir
`dev` (o la rama que se esté probando a propósito) y ningún cambio: **desde la
máquina nunca se commitea**, sólo se trae lo que ya está subido.

```bash
ssh vmuser@gongarcia.tfg.etsii.urjc.es 'cd ~/2026-ClickBaitAnalysis && git branch --show-current && git status --short'
```

Traer lo último y reconstruir. `--wait` no vuelve hasta que los tres servicios
están sanos. Con todo en la caché de compilación tarda unos 25 s; si cambian las
fichas de los modelos se rehace su capa, un par de minutos más. Se usa
`sudo docker`, no el grupo `docker` (el porqué, en la sección de #164).

```bash
ssh vmuser@gongarcia.tfg.etsii.urjc.es 'cd ~/2026-ClickBaitAnalysis && git pull --ff-only && sudo docker compose up --build --wait'
```

⚠️ **El registro de la API es del contenedor y se pierde al recrearlo.** Lo que
se quiera citar de una prueba se lee antes de desplegar, con
`bash spikes/chat_registro.sh` desde WSL.

Comprobarlo desde fuera (`-k` porque el certificado es autofirmado). Sin sesión
de GPU, `availability.status` sale `unreachable`: el asistente está configurado
y apagado.

```bash
curl -sk --max-time 10 https://gongarcia.tfg.etsii.urjc.es/api/agent
```

### Máquina 1: pararla

Normalmente no se para: con `restart: unless-stopped`, la aplicación vuelve sola
tras un reinicio de la máquina. Si hace falta pararla:

```bash
ssh vmuser@gongarcia.tfg.etsii.urjc.es 'cd ~/2026-ClickBaitAnalysis && sudo docker compose down'
```

`down` conserva el historial, que vive en un volumen; **`down -v` lo borra**.
Para volver a levantarla, el paso de desplegar.

### Máquina 2: encender el asistente

`gpu-sesion` (instalación, más abajo) comprueba antes que nadie esté usando la
GPU: con una terminal delante pregunta, y sin ella no abre. Ollama tarda unos
27 s en responder, porque la GPU tiene el modo persistente desactivado (#181), y
el asistente está disponible cuando la comprobación de arriba
(`curl … /api/agent`) dice `available`. La primera conversación carga además
el modelo, unos 8 s más.

**Con una terminal abierta**, que es lo normal. Abre una shell en la máquina 2
con Ollama y el túnel detrás, y la sesión dura lo que dure esa shell. Lleva `-t`
porque sin comando `gpu-sesion` abre una shell, y la ruta completa porque un
`ssh` con comando no lee `~/.profile`, que es quien pone `~/bin` en el `PATH`.

```bash
ssh -t gongarcia@gserver2.tfg.etsii.urjc.es 'GPU_SESION_MAX=1h ~/bin/gpu-sesion'
```

**Sin dejar una terminal abierta.** La sesión se desacopla de la conexión y
espera a un fichero testigo; lo que escribe `gpu-sesion` queda en
`/tmp/gpu_sesion.log` de la máquina 2, y si alguien estaba usando la GPU, allí
dice que no se abrió. El comando empieza borrando el testigo de una sesión
anterior: si quedara uno, la nueva se cerraría nada más abrirse. Desde bash
(WSL o Git Bash): PowerShell pierde las comillas dobles de dentro del comando.

```bash
ssh -T -o BatchMode=yes gongarcia@gserver2.tfg.etsii.urjc.es 'rm -f /tmp/gpu_sesion_fin; GPU_SESION_MAX=1h setsid nohup ~/bin/gpu-sesion bash -c "until [ -e /tmp/gpu_sesion_fin ]; do sleep 2; done" > /tmp/gpu_sesion.log 2>&1 < /dev/null & disown'
```

### Máquina 2: apagar el asistente

- **Con terminal**: `exit` o Ctrl-D en la shell de la sesión. Cerrar la ventana
  también la cierra. Ctrl-C no: en el prompt, una shell interactiva lo ignora.
- **Sin terminal**: crear el testigo.

  ```bash
  ssh gongarcia@gserver2.tfg.etsii.urjc.es 'touch /tmp/gpu_sesion_fin'
  ```

- **Si nadie la cierra**, se cierra sola al agotar `GPU_SESION_MAX`.

En los tres casos se cierra primero el túnel —la API deja de ver el modelo— y
después Ollama, y `gpu-sesion` escribe «GPU liberada.». Matar el proceso de
`gpu-sesion` no sirve: mientras corre su comando, bash deja las señales para
cuando termine; y con `kill -9` se saltaría la limpieza y Ollama quedaría
encendido.

**Después, siempre, comprobar que la GPU queda libre**: tiene que salir `0 MiB`
y `0`.

```bash
ssh gongarcia@gserver2.tfg.etsii.urjc.es 'nvidia-smi --query-gpu=memory.used --format=csv,noheader; pgrep -u gongarcia -c -x ollama'
```

Si queda un Ollama propio, se para sólo ése. Los corchetes hacen falta: sin
ellos, `pkill -f` se encuentra a sí mismo en la línea de comandos de la sesión
SSH y la mata antes de terminar. Nunca se tocan procesos de otros usuarios.

```bash
ssh gongarcia@gserver2.tfg.etsii.urjc.es "pkill -u gongarcia -f '[o]llama serve'"
```

`gpu-sesion` escribe el registro de Ollama desde cero en cada sesión: lo que se
quiera citar de una se lee antes de abrir la siguiente, con
`bash spikes/ollama_registro.sh` desde WSL.

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
