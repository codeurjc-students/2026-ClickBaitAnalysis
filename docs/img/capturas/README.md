# Capturas de la versión servida

*No se edita a mano: lo escribe `spikes/capturas.mjs` (#215) junto con las
imágenes y la lista de cada recorrido (`<recorrido>.json`). La orden para
repetirlas está en su cabecera.*

Sitio: https://gongarcia.tfg.etsii.urjc.es. Ventana: 1280×800 píxeles CSS a escala 2, tema claro, `es-ES`.

## Las pantallas (`pantallas`)

| Condición | Valor |
|---|---|
| Fecha | 2026-11-21 23:13, hora de Madrid |
| Commit servido | `79f029e`, el del clon de la máquina 1 (0 ficheros cambiados en él) |
| Versión del contrato | 1.0.0 |
| Navegador | Edg/157.0.4341.60, sin ventana |

| Fichero | Qué enseña | Píxeles | Tamaño |
|---|---|---|---|
| [`01-formulario.png`](01-formulario.png) | La pantalla de análisis (`/analizar`) antes de analizar: el formulario y los cuatro titulares de ejemplo. | 2560×1600 | 102 KB |
| [`02-clickbait.png`](02-clickbait.png) | El resultado del ejemplo «clickbait claro», tal como se abre: lo que cabe sin desplazar. Veredicto: «Clickbait de forma». | 2560×1600 | 212 KB |
| [`03-clickbait-entero.png`](03-clickbait-entero.png) | El mismo resultado, la página entera, con todas las tarjetas de señal abiertas. | 2560×2960 | 344 KB |
| [`04-ambiguo-entero.png`](04-ambiguo-entero.png) | El resultado del ejemplo «caso ambiguo», la página entera, con todas las tarjetas abiertas. Veredicto: «Ambiguo». | 2560×3000 | 329 KB |
| [`05-espanol-entero.png`](05-espanol-entero.png) | El resultado del ejemplo «en español», la página entera, con todas las tarjetas abiertas. Veredicto: «Clickbait de forma». | 2560×2892 | 328 KB |
| [`06-salud.png`](06-salud.png) | El indicador de salud de la cabecera, desplegado: las APIs externas que se sondean y su estado. | 2560×1600 | 243 KB |
| [`07-historial.png`](07-historial.png) | El historial (`/historial`): las entradas más recientes, de análisis y de ejecuciones sueltas. | 2560×1600 | 221 KB |
| [`08-sistema.png`](08-sistema.png) | Sistema (`/sistema`): el servidor MCP conectado y el principio del catálogo de herramientas. | 2560×1600 | 166 KB |
| [`09-sistema-ejecucion.png`](09-sistema-ejecucion.png) | Una ejecución suelta desde Sistema: `analyze_sentiment` con «10 Amazing Things You Won't Believe», el formulario que sale de su esquema y la respuesta. | 2560×1600 | 157 KB |
| [`10-asistente-apagado.png`](10-asistente-apagado.png) | El asistente (`/asistente`) sin el modelo en marcha (sin sesión de GPU): explica por qué no se puede usar, en vez de ofrecer un chat que fallaría. | 2560×1600 | 99 KB |

Cada ejecución deja en producción tres análisis y una ejecución suelta, que quedan en el historial. De una ejecución a otra cambian, aunque el código sea el mismo, las horas, el estado de las APIs externas y lo que haya en el historial.

## El asistente, con el modelo en marcha (`asistente`)

| Condición | Valor |
|---|---|
| Fecha | 2026-11-21 23:29, hora de Madrid |
| Commit servido | `79f029e`, el del clon de la máquina 1 (0 ficheros cambiados en él) |
| Versión del contrato | 1.0.0 |
| Navegador | Edg/157.0.4341.60, sin ventana |
| Modelo | `qwen3.5:27b`, con el prompt `06-dato` (de `/api/agent`) |

| Fichero | Qué enseña | Píxeles | Tamaño |
|---|---|---|---|
| [`11-asistente-conversacion.png`](11-asistente-conversacion.png) | La segunda conversación del paso 6 de `docs/demostracion.md`, ya en caliente, tal como queda: las tres preguntas, lo que consultó el asistente en cada turno y su respuesta. Turnos: 1, `analyze_headline` (respondió); 2, `detect_clickbait_linear` (respondió); 3, `analyze_headline` (respondió). | 2560×7416 | 863 KB |
| [`12-asistente-conversacion-tarjetas.png`](12-asistente-conversacion-tarjetas.png) | La misma conversación, con las 4 tarjetas de señal que estaban plegadas abiertas. | 2560×8122 | 921 KB |

Cada ejecución deja en producción seis turnos del asistente, que no guarda nada en el historial (H5). De una ejecución a otra cambian, aunque el código sea el mismo, las horas, el estado de las APIs externas y lo que haya en el historial.
