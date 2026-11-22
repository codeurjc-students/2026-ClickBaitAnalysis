# ClickBait Analysis

> El diario del desarrollo —cada issue, con lo que se decidió, lo que se midió
> y lo que se descartó— está en [`docs/diario.md`](docs/diario.md). Hasta el 22
> de noviembre de 2026 era este README.

Trabajo de Fin de Grado: **desarrollo de un agente inteligente basado en MCP
para la detección y análisis de *clickbait* en medios digitales, con interfaz
web**.

El sistema analiza titulares de noticias, en inglés y en español, sin dar un
veredicto único de caja negra. Contrasta varias señales de distinta naturaleza
—un léxico de pistas y un modelo lineal, que se pueden leer; la similitud entre
el titular y su texto, a medio camino; y modelos afinados, que no— y cada una
dice qué es y hasta dónde llega. Las herramientas se publican en un servidor
[MCP](https://modelcontextprotocol.io/), que usan una API REST, una interfaz
web y un asistente conversacional con un modelo de lenguaje local.

- **En producción**: <https://gongarcia.tfg.etsii.urjc.es>. El asistente sólo
  responde mientras hay una sesión de GPU abierta; el resto, siempre.
- **La versión**: `v1.0.0`, el código congelado el 21 de noviembre de 2026 en
  `79f029e`.

## La documentación

Ordenada como la memoria del TFG, que copia de aquí sus secciones:

| Documento | Qué cuenta | En la memoria |
|---|---|---|
| [Objetivos](docs/objetivos.md) | El problema, qué se quería conseguir y el alcance | Capítulo 1 |
| [Metodología](docs/metodologia.md) | Cómo se organizó el trabajo: fases, hitos, issues y ramas | Capítulo 2 |
| [Funcionalidades](docs/funcionalidades.md) | Qué hace el sistema, pantalla a pantalla, con capturas de la versión congelada | Capítulo 3 |
| [Requisitos](docs/requisitos.md) y su [estado](docs/arquitectura.md#estado-de-los-requisitos) | Los criterios de aceptación y cómo se cumple cada uno | Anexo A |
| [Ejecución](docs/ejecucion.md) | Cómo se levanta el sistema entero con Docker, en cualquier máquina | Anexo B |
| [Desarrollo](docs/desarrollo.md) | Cómo se edita el código: el entorno, las pruebas y las convenciones | Anexo C |
| [Arquitectura](docs/arquitectura.md) | Las capas, el despliegue y el agente, con sus diagramas | Capítulo 4 |
| [Estructura](docs/estructura.md) | Dónde vive cada cosa en el repositorio, y por qué | Capítulo 4 |
| [Demostración](docs/demostracion.md) | El guion de la demostración de la defensa, con sus planes B y C | — |
| [Diario](docs/diario.md) | La historia del desarrollo, issue a issue | Todo |

Para operar las máquinas de la universidad (desplegar, encender el asistente y
apagarlo), [`despliegue/README.md`](despliegue/README.md).
