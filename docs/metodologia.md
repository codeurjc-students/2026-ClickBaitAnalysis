# Metodología

Resumen del capítulo 2 de la memoria. Las reglas del día a día (ramas,
commits, versiones y cuándo se etiqueta) están en
[`desarrollo.md`](desarrollo.md#10--convenciones-de-desarrollo), y el plan de
trabajo detallado, con sus hitos, al principio del [diario](diario.md).

## Iterativo e incremental

El trabajo se desarrolló entre febrero de 2026 y febrero de 2027. Desde julio,
cada bloque terminado se publicó como una versión que se puede usar.

Las fases no se fijaron de antemano: reflejan cómo se aprendió a organizar el
trabajo.

1. **Experimentación**, sin una organización clara.
2. **Épicas**: bloques de trabajo sobre un mismo tema, sin fecha.
3. **Hitos**: puntos de control con fecha. Salvo el primero, que fue de diseño,
   cada uno se cierra publicando una versión.

Dentro de un hito, la unidad de trabajo es la *issue*. Cada una lleva una rama,
una *pull request* y un *squash merge* a `dev`, y deja su sección en el diario,
con lo que se decidió, lo que se midió y lo que se descartó.

## Las fases

| Fase | Inicio | Fin | Qué deja |
|---|---|---|---|
| Experimentación | 24 feb | 20 abr | prototipos del servidor MCP, con una API del tiempo y la primera fuente de noticias |
| Épicas | 20 abr | 19 jul | el núcleo de análisis (`v0.2.0`) |
| Hitos | 2 ago | 11 oct | la aplicación web, su puesta en producción, el agente y el análisis en español (`v0.3.0` a `v0.8.0`) |
| Definición de las funcionalidades | 5 jun | 4 ago | los requisitos (5 jun) y el diseño de la interfaz (desde el 16 jul) |
| Controles de calidad | 19 may | 21 nov | comprobaciones automáticas en cada cambio, hasta la congelación del código |
| Memoria | 11 oct | 31 dic | la memoria; las correcciones, en enero |
| Presentación | 12 nov | feb 2027 | la demostración, con su guion y un ensayo, y la defensa |

## Las versiones

| Versión | Fecha | Qué trae |
|---|---|---|
| `v0.2.0` | 19 jul 2026 | el núcleo de análisis |
| `v0.3.0` | 15 ago | la API REST |
| `v0.4.0` y `v0.4.1` | 7 sep | la interfaz web, y su corrección |
| `v0.5.0` | 20 sep | la puesta en producción |
| `v0.6.0` | 1 oct | el agente conversacional |
| `v0.7.0` | 7 oct | lo que el agente dejó abierto, la jerarquía del veredicto y el lineal reentrenado |
| `v0.8.0` | 11 oct | el análisis en español |
| `v1.0.0` | — | el código congelado el 21 nov en `79f029e`: la versión que describe la memoria |

## Lo que pasó de verdad

- **Las fases se solaparon.** Los requisitos se escribieron en junio, con las
  épicas ya en marcha. Al diseñar la interfaz se vio que no recogían el agente
  conversacional, que da nombre al trabajo, y se añadió. Los controles de
  calidad crecieron a medida que el código los pedía, y la memoria empezó con
  el desarrollo abierto.
- **El desarrollo fue casi tres meses por delante del plan.** El plan por
  hitos, del 2 de agosto, fijaba la entrega en febrero de 2027:
  - la API, prevista para octubre, se publicó el 15 de agosto;
  - la interfaz web, prevista para noviembre, el 7 de septiembre;
  - y la puesta en producción, prevista entre diciembre y enero, el 20 de
    septiembre.

  Con ese adelanto, el agente conversacional, que en el plan no tenía fecha,
  tuvo un hito propio sin mover la entrega.
- **La congelación del código se adelantó** del 15 de diciembre al 21 de
  noviembre, por decisión del autor. Desde entonces sólo entran arreglos y lo
  que pida la defensa, y lo que no se cerró está en la issue de trabajo
  futuro (#217).
