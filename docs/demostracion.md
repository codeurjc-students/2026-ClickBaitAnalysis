# Demostración

El guion para enseñar el sistema en directo en la defensa, sobre la versión
congelada el 15 de diciembre de 2026: qué se comprueba antes, qué se enseña y en
qué orden, y qué se hace si algo falla. Los comandos de las máquinas no se
repiten aquí: están en
[«El día a día»](../despliegue/README.md#el-día-a-día-desplegar-encender-el-asistente-y-apagarlo)
de `despliegue/README.md`. El porqué de cada decisión está en el README
principal, en la sección de #214.

**Lo que falta**, y a qué espera:

| Qué | Espera a |
|---|---|
| El ensayo completo, con lo que tarda cada parte | nada: la máquina 1 sirve la grabación desde el 13 nov |
| El plan C: la grabación en vídeo y las capturas | la congelación |

## Lo que se enseña

Cuatro pantallas, en este orden: **Analizar**, **Historial**, **Sistema** y
**Asistente**. El hilo es el del trabajo: el sistema no emite un veredicto de
caja negra, sino que contrasta señales de distinta naturaleza y enseña de dónde
sale cada cosa.

El asistente va el último a propósito. Es lo único que depende de la máquina 2,
que es compartida: si ese día no se puede usar, todo lo anterior ya se ha
enseñado, y el análisis funciona sin ella.

## La víspera

1. **La máquina 1 sirve la versión congelada**: la rama y el commit del clon, y
   que no tenga cambios («Máquina 1: desplegar»).
2. **Responde desde fuera**, con el certificado válido y las 14 herramientas en
   `ok`:

   ```bash
   bash spikes/certificado_en_vivo.sh
   ```

   ```bash
   .venv/bin/python spikes/produccion_en_vivo.py
   ```

3. **Los titulares del guion dan lo que dice el guion.** Son deterministas: si
   alguno ha cambiado, el guion se corrige esa tarde, no en la sala. Sobre el
   commit congelado, y después los tres de Analizar a mano, en la web:

   ```bash
   CUDA_VISIBLE_DEVICES= .venv/bin/python spikes/demostracion_titulares.py
   ```
4. **El asistente, entero**: una sesión de GPU corta, la conversación del paso 6
   y la noticia del paso 7, cerrar la sesión y comprobar la GPU a 0 MiB
   («Máquina 2: apagar el asistente»).
5. **Los planes B y C, a mano.**
   - **El plan B se reproduce entero sobre el commit congelado.** Sin modelo:
     las tres preguntas del paso 6 pasan por el agente con las herramientas de
     verdad, y el guion falla si algún turno no narraría lo grabado.

     ```bash
     CUDA_VISIBLE_DEVICES= .venv/bin/python spikes/grabar_demostracion.py --reproducir
     ```

     Y en la máquina 1, como lo vería la pantalla: encenderlo, comprobarlo con
     `--reproducir-en` y volver al modelo («Máquina 1: el asistente con
     respuestas grabadas»). Si algún turno no se reproduce, alguna herramienta
     ya no da lo que se grabó y la grabación no vale para la versión
     congelada: hay que grabar otra (#265), y eso pide una sesión de GPU. Por
     eso conviene comprobarlo ya al congelar, y no sólo la víspera.
   - **El plan C**: el vídeo y las capturas, en el equipo de la presentación y
     en una memoria USB.
6. **Una segunda red**: el móvil, como punto de acceso. El 30 de septiembre la
   universidad bloqueó la IP de casa, y la web seguía respondiendo desde otra
   red (#193).
7. **Los textos del guion, en un fichero abierto**, para pegarlos: escribir un
   titular largo delante del tribunal es lento, y una errata cambia el
   resultado. Están al final de «El guion».

## Antes de empezar

Unos 15 minutos antes de la defensa:

1. **Abrir la sesión de GPU**, con una terminal delante y un tope que cubra la
   defensa con margen. Es el comando de «Máquina 2: encender el asistente» con
   otro tope (por defecto son 2 h):

   ```bash
   ssh -t gongarcia@gserver2.tfg.etsii.urjc.es 'GPU_SESION_MAX=3h ~/bin/gpu-sesion'
   ```

   Si `gpu-sesion` pregunta porque hay otro proceso en la GPU, **no se abre**:
   es una máquina compartida. Se pasa al plan B.
2. **Esperar a que el asistente esté.** Ollama tarda unos 27 s en responder, y
   `/api/agent` pasa a decir `available` (el comando, en «Máquina 1:
   desplegar»). Se pregunta a la API, y una vez: a la máquina 2 no se la sondea.
3. **Calentar con la conversación del paso 6, entera.** Hace dos cosas:
   - carga el modelo en la GPU: unos 8 s, pero tras un reinicio de la máquina 2
     fueron 105 s (15 oct 2026);
   - carga en el servidor MCP los modelos de las señales, en inglés y en
     español. La API los precalienta al arrancar (`PREHEAT_MODELS`) y el
     servidor MCP no, así que el primer análisis del asistente en cada idioma
     los carga dentro de la llamada.

   Al acabar, «Empezar una conversación nueva»: la conversación se guarda en la
   pestaña y, si no, seguiría ahí al llegar al paso 6.
4. **Esperar un minuto.** La API admite 10 análisis o turnos de chat por minuto
   y por IP; calentar y empezar seguido puede dar un «Demasiadas peticiones
   seguidas».
5. **El navegador**: la web abierta en Analizar, con un tamaño de letra que se
   lea desde el fondo de la sala, y el fichero de textos al lado.

**El modelo se descarga de la GPU a los 10 minutos sin uso** (`LLM_KEEP_ALIVE`).
Con la exposición por delante, lo normal es que al llegar al paso 6 ya no esté
cargado: la primera pregunta lo vuelve a cargar. Con el fichero ya en la caché
de disco, cargarlo cuesta unos 8 s (de 7,6 a 7,9 s en las cuatro sesiones
siguientes a la del reinicio, el 15 oct). No hace falta otra pregunta de
calentamiento: se cuenta con esos segundos, y el ensayo los mide.

## El guion

Unos ocho minutos. Los pasos 2 y 4 se pueden saltar si hay que recortar: sin
ellos, siete. **Los tiempos son previstos**; los medidos, en «El ensayo».

| Paso | Pantalla | Qué se enseña | Previsto |
|---|---|---|---|
| 1 | Analizar | Un titular con su cuerpo: el veredicto y las cinco señales | 90 s |
| 2 | Analizar | Un titular en el que las señales discrepan *(recortable)* | 45 s |
| 3 | Analizar | Un titular en español | 45 s |
| 4 | Historial | Lo analizado queda guardado y se puede volver a abrir *(recortable)* | 30 s |
| 5 | Sistema | Las herramientas del servidor MCP y las fichas de los modelos | 60 s |
| 6 | Asistente | Una conversación de tres turnos, con la traza a la vista | 150 s |
| 7 | Asistente | Trae una noticia y analiza su titular | 75 s |

Los veredictos y las cifras de los titulares salen de
`spikes/demostracion_titulares.py`, que falla si alguno deja de ser el de aquí
(12 de noviembre de 2026, sobre `2aabb7c`, en CPU). «Se dice» son las ideas de
cada paso, no frases para leer.

### 1 · Analizar: las cinco señales

- **Se hace**: pegar el titular A y su cuerpo, y «Analizar».
- **Se ve**: el veredicto, **Engañoso**; el titular con las pistas resaltadas;
  las dos dimensiones, forma y engaño; y las cinco señales, cada una con su
  tipo. Al abrir las tarjetas:

  | Señal | Tipo | Resultado |
  |---|---|---|
  | Dedicada (RoBERTa) | opaca | clickbait, 0,97 |
  | Léxico | interpretable | 5 pistas, con el umbral en 1 |
  | Lineal | interpretable | probabilidad 0,99, con el umbral en 0,35 |
  | Incoherencia | híbrida | similitud 0,08, con el umbral en 0,3 |
  | Tono | opaca | neutral; no vota |

- **Se dice**:
  - no hay un número único: son cinco señales de tres naturalezas, y cada una
    declara su tipo y su umbral;
  - en las interpretables, la explicación es el propio resultado: las pistas
    del léxico y los pesos del lineal, palabra a palabra;
  - el veredicto sale de una jerarquía explícita, no de un promedio: la forma
    dice «clickbait», y la incoherencia añade que el titular y el cuerpo no
    hablan de lo mismo;
  - el tono se enseña y no vota.

### 2 · Analizar: cuando las señales discrepan *(recortable)*

- **Se hace**: «Nuevo análisis», el ejemplo «caso ambiguo» del formulario y
  «Analizar».
- **Se ve**: el veredicto, **Ambiguo**. La dedicada dice clickbait (0,86) y el
  lineal da 0,76, muy por encima de su umbral, 0,35; el léxico no encuentra
  ninguna pista. Sin cuerpo, la incoherencia no se aplica.
- **Se dice**:
  - el sistema declara la discrepancia en vez de esconderla en una media;
  - se ve por qué discrepan: el gancho está al final, «Here's Why». Las listas
    del léxico no lo recogen, y el lineal sí lo aprendió: sus tres palabras con
    más peso son *here's*, *why* y *just*. Con un modelo de caja negra solo,
    este titular tendría un «sí» al 86 % y nada más.

  *De repuesto, si el ejemplo cambiara: el titular C con el cuerpo C, que
  también da Ambiguo, con la forma unánime en «no» y la incoherencia en «sí».*

### 3 · Analizar: un titular en español

- **Se hace**: «Nuevo análisis», el ejemplo «en español» del formulario y
  «Analizar».
- **Se ve**: el veredicto, **Clickbait de forma**. La dedicada es otro modelo,
  BETO afinado en este proyecto (clickbait, 0,99); el lineal da 0,43; y el
  léxico y la incoherencia salen como no aplicables, cada una con su motivo a
  la vista: el titular parece estar en español.
- **Se dice**:
  - el idioma se detecta, y cada señal se ejecuta sólo si analiza ese idioma;
  - los dos «no se aplica» son de distinta clase: el léxico es una decisión (sus
    listas son de titulares en inglés), y la incoherencia, una medida (en
    español se probó y apenas distingue el clickbait);
  - el sistema dice lo que no sabe hacer, en vez de dar un número.

### 4 · Historial *(recortable)*

- **Se hace**: ir a Historial y abrir el primer análisis de la lista.
- **Se ve**: los tres análisis recién hechos, con su veredicto, y la misma
  pantalla de resultado con el aviso «Recuperado del historial».
- **Se dice**: lo que se guarda es el resultado entero, así que se vuelve a ver
  tal como salió.

### 5 · Sistema

- **Se hace**: ir a Sistema y bajar por sus tres bloques: Servidores MCP,
  Herramientas y Fichas de modelo. Abrir los límites de una ficha.
- **Se ve**: el servidor MCP conectado, sus 14 herramientas y, de cada modelo,
  qué es, de qué tipo y sus límites medidos.
- **Se dice**:
  - el catálogo no está escrito en la web: sale del servidor MCP, y son las
    mismas herramientas que va a usar el asistente;
  - cada modelo publica sus límites, con las cifras de la evaluación.

### 6 · Asistente: una conversación de tres turnos

Cada pregunta nombra su titular. A un «¿por qué?» a secas, el asistente
contestó sin llamar a ninguna herramienta en 6 de 20 (#208).

- **Se hace**: ir a Asistente y enviar las tres preguntas, una detrás de otra.
  Mientras responde la primera, abrir «Sobre el asistente».
- **Se ve**, en cada turno, la traza antes que el texto: qué herramienta
  consulta, su resultado pintado con las mismas tarjetas que en Analizar y,
  debajo, la narración.

  | Turno | Herramienta esperada | Resultado |
  |---|---|---|
  | 1 | `analyze_headline` | Clickbait de forma: dedicada 0,95, léxico 4 pistas, lineal 0,99 |
  | 2 | `detect_clickbait_linear` | los pesos: *this* 1,90, *you* 1,75, *what* 1,14 |
  | 3 | `analyze_headline` o una señal | en español; el análisis del paso 3 |

- **Se dice**:
  - el veredicto no lo escribe el modelo: lo calcula la herramienta, y la
    pantalla pinta el resultado de la herramienta, no el texto;
  - en el turno 2 elige la señal interpretable porque se le pregunta por los
    pesos: lo único que el modelo sabe de cada herramienta es su nombre, su
    descripción y sus parámetros;
  - «Sobre el asistente» enseña qué modelo es, sus límites medidos y el prompt
    en uso.

### 7 · Asistente: una noticia, en vivo

Es el único paso que no se puede grabar, porque las noticias cambian cada día,
y el que más falla: va el último, y si se tuerce no arrastra nada.

- **Se hace**: enviar la pregunta de la noticia.
- **Se ve**: la lista de noticias de `get_nyt_news`, con sus enlaces, y después
  el análisis de uno de sus titulares: la tarjeta de una señal, o el resultado
  completo.
- **Se dice**: encadena dos herramientas, y la segunda recibe lo que trajo la
  primera.
- **Si narra cifras y no hay ninguna tarjeta de señal**, sólo la lista de
  noticias, **se las ha inventado**. Se dice tal cual —es un límite medido, y
  está en la ficha del asistente— y se pega ese titular en Analizar para
  enseñar el resultado de verdad.

### Los textos

Titular A y cuerpo A (paso 1):

```text
10 Secrets Doctors Won't Tell You... Are You Ready?
```

```text
A small study in mice found modest effects of the diet after eight weeks.
```

Titular B (paso 2), por si hubiera que pegarlo: es el del ejemplo «caso
ambiguo».

```text
The Federal Reserve Just Held Interest Rates Steady. Here's Why
```

Titular C y cuerpo C (el repuesto del paso 2):

```text
Federal Reserve raises interest rates by a quarter point
```

```text
The local football team won the championship after a dramatic penalty shootout on Sunday night.
```

Las tres preguntas del paso 6:

```text
Analiza a fondo el titular 'You Won't Believe What This Dog Did Next' con todas las señales del sistema.
```

```text
¿Con qué peso contribuye cada palabra de 'You Won't Believe What This Dog Did Next' al veredicto?
```

```text
¿Es clickbait 'No vas a creer lo que hizo este perro al ver a su dueño'?
```

La pregunta del paso 7:

```text
Busca una noticia del New York Times sobre inteligencia artificial y dime si su titular es clickbait.
```

## Si algo falla

| Qué se ve | Qué es | Qué se hace |
|---|---|---|
| `gpu-sesion` pregunta antes de abrir | Otra persona está usando la GPU | No se abre. Plan B |
| `/api/agent` no llega a `available`, o Asistente dice «Ahora mismo no se puede usar» | El modelo no está: Ollama o el túnel | Cerrar la sesión y abrirla una vez más. Si sigue igual, plan B |
| Una respuesta tarda | El modelo razona antes de contestar. La pantalla dice en qué fase está y cuánto lleva, y al minuto avisa de que puede tardar un par | Seguir con «Sobre el asistente». Cada vuelta del modelo tiene un tope de 300 s; la conversación más larga medida con los arreglos de #208, 117 s |
| «El asistente no escribió un resumen» | Una respuesta vacía | Nada: las tarjetas están, y son lo que cuenta |
| El asistente termina con un error | Agotó el tiempo o falló una llamada | Repetir la pregunta, una vez |
| Narra cifras sin ninguna tarjeta de señal | Se las ha inventado | Decirlo y cotejar el titular en Analizar (paso 7) |
| «Demasiadas peticiones seguidas» | El límite de 10 por minuto | Esperar los segundos que dice el mensaje |
| `get_nyt_news` falla o no trae nada | La API de noticias o su cuota | Repetir la pregunta con «de The Guardian». Si tampoco, se salta el paso 7 |
| La web no carga | La red de la sala, o un bloqueo de la IP | El móvil como punto de acceso. Si tampoco, plan C |

### Plan B: el asistente con respuestas grabadas

Cuando no hay modelo: `gpu-sesion` no abre, o `/api/agent` no llega a
`available` (las filas de arriba que dicen «Plan B»). La API reproduce lo que
escribió el 27B al grabar la conversación del paso 6, y las herramientas se
ejecutan de verdad: las tarjetas son de ese momento, y sólo el texto del modelo
es grabado (#265). No necesita la máquina 2.

La grabación es la toma 2 de tres, del 13 de noviembre de 2026, con
`qwen3.5:27b` sobre `147d1df` y `06-dato`, elegida con la regla que se publicó
en #265 antes de grabar.

- **Se enciende** desde WSL, con el comando de
  [«Máquina 1: el asistente con respuestas grabadas»](../despliegue/README.md#máquina-1-el-asistente-con-respuestas-grabadas)
  de `despliegue/README.md`. Recrea sólo la API, y mientras arranca tampoco
  responde el análisis: en la máquina 1, el cambio tardó 13 o 14 s, y la
  vuelta, 14 (dos veces, el 13 nov 2026; en la pila local, 19 y 18).
- **Se calienta como con el modelo**: la conversación del paso 6 entera, y
  «Empezar una conversación nueva». No hay modelo que cargar, pero el servidor
  MCP carga los de las señales en su primera llamada: en la máquina 1, con el
  servidor MCP recién arrancado, el turno 1 tardó 8 s y los otros dos, 2; ya
  caliente, los tres tardaron 2.
- **Se ve**, en Asistente, un aviso fijo de que son respuestas grabadas, de qué
  modelo y de qué día, y «Sobre el asistente» enseña la ficha de la grabación.
- **Se hace** el paso 6, con las mismas tres preguntas, pegadas de «Los
  textos». A cualquier otra pregunta contesta que no está grabada, y dice
  cuáles lo están.
- **Se dice** que es el mismo modelo, grabado, y que las tarjetas no lo son: si
  una herramienta no diera lo que se grabó, el asistente no narraría lo
  grabado, y lo diría.
- **El paso 7 no se hace**: las noticias cambian cada día y no se graban. Con
  el plan B, la demostración termina en el paso 6.
- **Si responde que «lo que recibe el modelo ha cambiado»**, alguna herramienta
  ha dado otra cosa que al grabar. Las tarjetas siguen siendo las de verdad: se
  enseñan, y se dice tal cual. Es lo que descarta la víspera (paso 5).

Al terminar, se vuelve al modelo con el comando de la misma sección.

### Plan C: el vídeo

**Pendiente de la congelación.** Una grabación de la versión congelada siguiendo
este mismo guion, y capturas de cada paso. No depende de la red ni de ninguna de
las dos máquinas. El enlace, aquí, cuando esté hecha.

## Al terminar

1. **Cerrar la sesión de GPU**: `exit` en su terminal. Tiene que escribir «GPU
   liberada.».
2. **Comprobar que la GPU queda libre**, a 0 MiB y sin ningún Ollama propio
   («Máquina 2: apagar el asistente»).
3. La máquina 1 se queda como está: sin sesión, la pantalla del asistente
   explica que está apagado, y el análisis sigue funcionando.

## El ensayo

**Pendiente.** Un ensayo completo, siguiendo este guion al pie de la letra,
sobre la máquina 1, y después el plan B. Se apunta lo que tarda cada parte y,
al acabar, la GPU a 0 MiB.

| Parte | Previsto | Medido |
|---|---|---|
| Antes de empezar, hasta `available` | — | |
| El calentamiento | — | |
| Paso 1 | 90 s | |
| Paso 2 | 45 s | |
| Paso 3 | 45 s | |
| Paso 4 | 30 s | |
| Paso 5 | 60 s | |
| Paso 6 | 150 s | |
| Paso 7 | 75 s | |
| Al terminar, hasta 0 MiB | — | |
| Plan B: el cambio, hasta `available` | 13–14 s | |
| Plan B: el paso 6, reproducido | — | |
| Plan B: la vuelta al modelo | 14 s | |
