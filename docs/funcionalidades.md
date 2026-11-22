# Funcionalidades

Qué hace el sistema, pantalla a pantalla, en la versión congelada (`79f029e`,
que se publica como `v1.0.0`). Todas las capturas son de producción, con la
misma ventana (1280×800 a escala 2); qué enseña cada una, cuándo se hizo y
cómo se repite, está en [su índice](img/capturas/README.md). Cada criterio de
los requisitos, con su estado, está en la
[tabla de estado](arquitectura.md#estado-de-los-requisitos).

La web tiene cuatro pantallas, una por pestaña: Asistente, Analizar, Historial y
Sistema. A la derecha de la cabecera, un indicador dice si responden las APIs de
noticias.

## Analizar un titular

Se escribe un titular y, si se tiene, el texto de la noticia, y se analiza. No
hay ningún modelo de lenguaje de por medio: se llaman todas las señales y se
contrastan entre sí. Cuatro botones rellenan el formulario con ejemplos: un
*clickbait* claro, un titular factual, un caso ambiguo y uno en español.

![El formulario de análisis, vacío](img/capturas/01-formulario.png)

El resultado empieza por el veredicto y el titular, con las palabras que han
pesado marcadas según su tipo de pista (por ejemplo, un número al principio,
una hipérbole o una referencia vaga). El veredicto responde a dos preguntas:

- **¿Tiene la forma del *clickbait*?** Lo deciden el léxico, el modelo lineal y
  el modelo dedicado, si analizan el idioma del titular.
- **¿Engaña respecto a su texto?** Lo decide la incoherencia entre el titular y
  el texto, y sólo si hay texto.

De ahí salen cinco veredictos: **Engañoso**, **Clickbait de forma**,
**Factual**, **Ambiguo** y **Sin datos**. Cuando las señales no coinciden, el
veredicto es «Ambiguo»: el desacuerdo se enseña, no se promedia. El tono
(positivo, neutro o negativo) se muestra, pero no vota.

![El resultado de un clickbait claro](img/capturas/02-clickbait.png)

Debajo va una tarjeta por señal. Cada una dice de qué tipo es (*interpretable*,
*hybrid* u *opaque*) y lo que da a cambio:

- el léxico, las pistas que encontró;
- el lineal, el peso de cada palabra;
- la incoherencia, la similitud entre el titular y el texto;
- los modelos afinados, su confianza, y que son una caja negra.

![El mismo resultado, entero y con todas las tarjetas abiertas](img/capturas/03-clickbait-entero.png)

En el caso ambiguo, las señales de la forma no coinciden, y el veredicto lo dice
en vez de elegir una:

![Un caso ambiguo](img/capturas/04-ambiguo-entero.png)

En español se usan otros modelos: BETO afinado con el corpus TA1C, el modelo
lineal, que es bilingüe, y otro modelo de tono. El léxico y la incoherencia no
analizan el español, y cada tarjeta dice por qué. Un titular en otro idioma no
recibe veredicto.

![Un titular en español](img/capturas/05-espanol-entero.png)

El indicador de la cabecera se despliega con el estado de cada API de noticias
que se sondea, y avisa de que las señales de análisis no se sondean ahí.

![El indicador de salud, desplegado](img/capturas/06-salud.png)

## Historial

Cada análisis y cada ejecución suelta de una herramienta quedan guardados. Se
filtran por tipo, por veredicto y por cómo terminó la ejecución, y se pasan por
páginas. Un análisis se vuelve a abrir tal como salió. Lo que hace el asistente
no se guarda.

![El historial](img/capturas/07-historial.png)

## Sistema

Lo que hay detrás:

- **los servidores MCP conectados**, con cuántas herramientas publica cada uno;
- **el catálogo de herramientas**, con un buscador y un filtro por categoría;
- **las fichas de los modelos**: su nombre, su tarea y sus límites medidos.

El catálogo se construye preguntando al servidor MCP, sin ninguna lista escrita
en la web.

![Sistema](img/capturas/08-sistema.png)

Cada herramienta se puede ejecutar suelta, con un formulario que sale del
esquema que publica, y se ve la respuesta tal cual:

![Una ejecución suelta de analyze_sentiment](img/capturas/09-sistema-ejecucion.png)

## El asistente

Se pregunta en lenguaje natural. El asistente, un modelo de lenguaje local
(`qwen3.5:27b`, servido por Ollama en una GPU de la universidad), elige qué
herramientas usar y cuenta lo que devuelven. El veredicto sale de las
herramientas, no de su texto.

Por cada pregunta se ve lo que consultó, con la tarjeta del resultado de cada
herramienta, y después su respuesta. Si una respuesta no se apoya en ninguna
herramienta, la pantalla lo avisa. La conversación se guarda en la pestaña del
navegador, y «Empezar una conversación nueva» la vacía. En «Sobre el asistente»
están su ficha y el prompt de sistema que usa.

![Una conversación](img/capturas/11-asistente-conversacion.png)

La captura con las tarjetas abiertas es
[`12-asistente-conversacion-tarjetas.png`](img/capturas/12-asistente-conversacion-tarjetas.png).

La GPU es compartida y se enciende bajo demanda. Sin ella, la pantalla dice que
el asistente está apagado y por qué, en vez de ofrecer un chat que fallaría. El
análisis sigue en Analizar.

![El asistente, apagado](img/capturas/10-asistente-apagado.png)

Para la demostración hay además un modo con las respuestas grabadas del modelo,
que reproduce una conversación ensayada con las herramientas de verdad. La
pantalla lo avisa siempre ([`demostracion.md`](demostracion.md)).

## Fuera de la web

- **La API REST**: lo que hacen las pantallas (analizar, el catálogo, ejecutar
  una herramienta, el historial, el asistente), documentado con OpenAPI en
  `/api/docs`.
- **El servidor MCP**: las mismas catorce herramientas, para cualquier cliente
  MCP. Por ejemplo, Claude Desktop ([`ejecucion.md`](ejecucion.md#desde-claude-desktop)).
