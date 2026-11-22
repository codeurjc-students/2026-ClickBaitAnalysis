# Objetivos

Resumen del capítulo 1 de la memoria. Qué se cumplió de cada objetivo, y cómo,
está en la [tabla de estado de los requisitos](arquitectura.md#estado-de-los-requisitos)
y en el capítulo 6.

## El problema

Leer noticias en internet tiene dos problemas que se suman. El primero, el
sensacionalismo: titulares escritos para despertar una emoción o una curiosidad
que el artículo no satisface, el *clickbait*. El segundo, la confianza en las
herramientas que prometen ayudar. Los sistemas de inteligencia artificial pueden
arrastrar sesgos, suelen ocultar cómo llegan a lo que dicen, y despiertan poca
confianza cuando escriben o editan noticias.

Este trabajo nace para ayudar a identificar los titulares sensacionalistas y, a
la vez, enseñar al usuario de dónde sale cada respuesta y cómo se obtuvo, de la
forma más transparente posible.

## Lo que ya existía

La detección automática de *clickbait* se ha abordado de tres maneras:

- **El aprendizaje automático clásico**: rasgos del texto y un clasificador.
  Por ejemplo, Potthast et al. (2016), sobre tuits, y Chakraborty et al.
  (2016), con listas de palabras típicas del *clickbait*. Este trabajo usa esas
  mismas listas, pero como reglas.
- **Las redes neuronales**, y hoy los *transformers* preentrenados (BERT,
  RoBERTa) afinados para la tarea. En español, el corpus TA1C de Mordecki et al.
  (2025), con un BETO afinado.
- **Preguntar a un modelo de lenguaje generativo**, sin entrenarlo. Los
  trabajos que lo han medido concluyen que, en general, no alcanza a los
  modelos afinados.

Hay también herramientas para el usuario final, pero ninguna combina las dos
cosas, detectar el *clickbait* y buscar noticias, ni enseña cómo obtiene y
evalúa la información.

**Este trabajo no elige una de las tres vías**: contrasta señales de varias,
cada una con su explicación, y da prioridad a las que se pueden interpretar por
sí mismas. El modelo de lenguaje no decide el veredicto: elige las herramientas
y cuenta lo que devuelven. Tampoco puede garantizar que no haya sesgo, porque,
por ejemplo, el orden de las noticias lo decide cada API. Lo que hace es
enseñar cada paso.

## Los objetivos

Son los objetivos con los que empezó el trabajo, tal como se plantearon.

### Funcionales

Una herramienta intuitiva y centralizada para obtener noticias e identificar las
que puedan ser engañosas o *clickbait*, mediante lenguaje natural:

- consultas en lenguaje natural, sin conocimientos técnicos, en una interfaz
  conversacional;
- la probabilidad de que un titular sea *clickbait*, con su confianza;
- el sentimiento de una noticia (positivo, negativo o neutro), con su
  confianza, y las palabras con más carga sensacionalista, marcadas;
- el proceso de cada respuesta a la vista: las herramientas usadas y las
  fuentes;
- noticias de medios externos por sus APIs, empezando por The Guardian;
- un historial de las consultas, para revisarlas sin repetirlas.

### Técnicos

El diseño buscaba transparencia, que el usuario vea el razonamiento, y
modularidad, para poder añadir APIs y herramientas:

- el backend en Python, con FastMCP y FastAPI;
- una arquitectura modular basada en el protocolo MCP;
- validar y sanear las entradas con Pydantic;
- la aplicación en contenedores, con Docker y Docker Compose;
- el frontend como una SPA en Angular;
- un pipeline de integración y despliegue continuos;
- los secretos y la configuración, en variables de entorno.

## Cómo evolucionaron

Durante el desarrollo, la transparencia pasó de ser sobre todo la del proceso
de la IA a ser también la de cada veredicto, que se convirtió en el eje del
trabajo. Algunos objetivos se cumplieron de otra manera:

- **las noticias, de cuatro APIs**: The Guardian, The New York Times,
  NewsData.io y GNews, estas dos en español;
- **el análisis, en inglés y en español**;
- **la entrada es el titular y, si se tiene, su texto**: analizar una noticia a
  partir de su URL quedó como trabajo futuro;
- **el despliegue se hace a mano**, a propósito, y lo justifica la historia de
  R8 en [`requisitos.md`](requisitos.md).

La historia de cada cambio está en el [diario](diario.md).
