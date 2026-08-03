# Requisitos

> Documento vivo: los requisitos pueden evolucionar durante el desarrollo. **Todo cambio queda registrado, con su motivo, en el [README](../README.md)** — en la sección de la épica o fase que lo originó.

## Introducción

Este documento define los requisitos para un Trabajo de Fin de Grado (TFG) que implementa un sistema de herramientas MCP (Model Context Protocol) en Python con interfaz web. El sistema permite crear, gestionar y ejecutar herramientas que consumen APIs públicas, con énfasis en análisis de texto mediante NLP, incluyendo detección de clickbait y análisis de sentimientos.

## Glosario

- **MCP_Server**: Servidor que implementa el protocolo MCP usando FastMCP SDK de Python.
- **MCP_Tool**: Herramienta individual que expone funcionalidad a través del protocolo MCP.
- **API_Consumer**: Componente que realiza llamadas a APIs públicas externas.
- **Web_Interface**: Aplicación Angular que permite interactuar con las herramientas MCP.
- **Tool_Catalog**: Sistema de registro y descubrimiento de herramientas disponibles.
- **NLP_Analyzer**: Componente que realiza análisis de procesamiento de lenguaje natural.
- **Backend_API**: API REST implementada con FastAPI que expone funcionalidad del servidor MCP.
- **Agent_Orchestrator**: Agente conversacional que interpreta consultas en lenguaje natural y decide qué MCP_Tools invocar (*tool calling*). Actúa como cliente MCP.
- **LLM_Backend**: Proveedor del modelo de lenguaje que usa el Agent_Orchestrator; intercambiable por configuración (local vía Ollama o API externa).
- **Docker_Environment**: Entorno de contenedores orquestado con Docker Compose.
- **CI_Pipeline**: Pipeline de integración continua implementado con GitHub Actions.

## Requisitos

### Requisito 1: Infraestructura de servidores MCP

**Historia de usuario:** Como desarrollador del sistema, quiero un servidor MCP funcional basado en FastMCP SDK, para que pueda exponer herramientas a través del protocolo MCP estándar.

**Criterios de aceptación:**

1. EL servidor MCP DEBERÁ inicializarse utilizando el SDK FastMCP del paquete oficial MCP Python.
2. CUANDO se inicie el servidor MCP, ÉSTE DEBERÁ cargar y registrar todas las herramientas MCP disponibles.
3. EL MCP_Server DEBERÁ exponer las herramientas a través de la interfaz de protocolo MCP estándar.
4. CUANDO se invoque una herramienta (tool), EL MCP_Server DEBERÁ enrutar la solicitud a la implementación MCP_Tool adecuada.
5. SI falla la ejecución de una herramienta, ENTONCES EL MCP_Server DEBERÁ devolver una respuesta de error estructurada con detalles.
6. EL MCP_Server DEBERÁ poder exponerse mediante **transporte HTTP** (`streamable-http`) además de `stdio`, para permitir su despliegue como contenedor independiente. _(Precondición del desacople: `stdio` exige que el cliente lance el servidor como subproceso, lo que no cruza contenedores.)_
7. EL sistema DEBERÁ admitir la conexión a **varios MCP_Server especialistas** declarados por configuración; añadir o retirar uno NO DEBERÁ requerir cambios de código.
8. SI un MCP_Server declarado no responde, ENTONCES el sistema DEBERÁ seguir operando con los restantes y reflejar su estado degradado.

### Requisito 2: Herramientas de integración de API públicas

**Historia de usuario:** Como usuario del sistema, quiero herramientas que consuman APIs públicas, para que pueda obtener información de servicios externos como meteorología y noticias.

**Criterios de aceptación** _(ejemplos de APIs, más a añadir):_

1. EL API_Consumer DEBERÁ implementar una herramienta meteorológica que recupere datos meteorológicos de una API meteorológica pública.
2. EL API_Consumer DEBERÁ implementar una herramienta de noticias que recupere artículos de noticias de una API pública de noticias.
3. CUANDO falle una solicitud de API, EL API_Consumer DEBERÁ gestionar el error correctamente y devolver un mensaje de error significativo.
4. EL API_Consumer DEBERÁ incluir una limitación de velocidad para respetar las restricciones de uso de la API.
5. CUANDO se reciban respuestas de la API, EL API_Consumer DEBERÁ validar la estructura de la respuesta antes de procesarla.
6. CUANDO se realice una llamada a la API, EL API_Consumer DEBERÁ rastrear el número de llamadas a la API utilizadas y registrarlo como **observabilidad interna** (logs). _(No se devuelve en la salida de la tool para no ensuciar la respuesta — ver memoria de cambios.)_
7. DONDE una API tenga límites de uso, EL API_Consumer DEBERÁ rastrear la cuota restante y registrarla como **observabilidad interna** (logs). _(Ver memoria de cambios.)_

### Requisito 3: Herramientas de análisis de texto con NLP

**Historia de usuario:** Como usuario del sistema, quiero herramientas de análisis de texto con NLP, para que pueda analizar sentimientos y detectar clickbait en contenido textual.

**Criterios de aceptación:**

1. EL NLP_Analyzer DEBERÁ implementar un análisis de sentimientos que clasifique el texto como positivo, negativo o neutro.
2. EL NLP_Analyzer DEBERÁ implementar una detección de clickbait que identifique si un titular es clickbait.
3. AL analizar el texto, EL NLP_Analyzer DEBERÁ devolver puntuaciones de confianza para sus clasificaciones.
4. EL NLP_Analyzer DEBERÁ admitir la entrada de texto en inglés. _(El soporte de español se pospone como mejora futura — ver memoria de cambios.)_
5. CUANDO el texto esté vacío o no sea válido, EL NLP_Analyzer DEBERÁ devolver un mensaje de error adecuado.
6. EL NLP_Analyzer DEBERÁ procesar las solicitudes de análisis de texto dentro de unos límites de tiempo razonables.
7. EL NLP_Analyzer DEBERÁ soportar la detección de clickbait por **incoherencia** entre el titular y su contenido (titular vs. teaser/cuerpo, o titular web vs. impreso), además de clasificar el titular de forma aislada. _(Requiere enriquecer la salida de las herramientas de noticias — ver Requisito 2.)_
8. EL NLP_Analyzer DEBERÁ acompañar cada veredicto de clickbait con una **explicación legible** de aquello en lo que se basa, **priorizando medios intrínsecamente interpretables** (marcas léxicas que disparan la señal y/o el grado de incoherencia titular↔contenido) frente a explicaciones post-hoc sobre modelos opacos. _(Eje de explicabilidad del TFG. Matiz: el score de incoherencia es transparente en su **decisión** pero su **feature** —embeddings— es opaca, y su umbral está sin calibrar — ver memoria de cambios.)_
9. EL NLP_Analyzer DEBERÁ **divulgar los modelos** que emplea (nombre, tarea y limitaciones conocidas) y DEBERÁ permitir **intercambiarlos por configuración**, sin cambios de código. _(Transparencia de sistema / model cards — ver memoria de cambios.)_
10. EL NLP_Analyzer DEBERÁ exponer **al menos dos señales independientes** de clickbait (p.ej. clasificación del titular e incoherencia titular↔contenido) que puedan **contrastarse** para reducir falsos positivos. _(La combinación **calibrada** de señales depende de un dataset etiquetado —ver E4-03—; el contraste inicial puede recaer en el agente orquestador.)_
11. DONDE se empleen clasificadores de caja negra (p.ej. zero-shot), EL NLP_Analyzer PODRÁ ofrecer explicaciones **post-hoc** por atribución (p.ej. LIME/SHAP) que resalten los términos más influyentes, **asumiendo sus límites de fidelidad**. _(Mejora opcional / comparativa de técnicas XAI.)_

### Requisito 4: API REST backend

**Historia de usuario:** Como desarrollador del frontend, quiero una API REST bien definida, para que pueda interactuar con el servidor MCP desde la interfaz web.

**Criterios de aceptación:**

1. La Backend_API DEBERÁ implementarse utilizando FastAPI.
2. La Backend_API DEBERÁ exponer un endpoint para enumerar todas las MCP_Tools disponibles con sus descripciones y parámetros.
3. La Backend_API DEBERÁ exponer un endpoint para ejecutar una MCP_Tool específica con los parámetros proporcionados.
4. La Backend_API DEBERÁ exponer un endpoint para recuperar el historial de ejecución de las herramientas.
5. CUANDO se reciba una solicitud de ejecución de una herramienta, LA Backend_API DEBERÁ validar los parámetros de entrada antes de la ejecución.
6. LA Backend_API DEBERÁ devolver respuestas en formato JSON con una estructura coherente.
7. LA Backend_API DEBERÁ incluir la configuración CORS para permitir las solicitudes de la aplicación frontend.
8. DONDE sea beneficioso para desarrollo y documentación, LA Backend_API PODRÁ incluir documentación automática usando OpenAPI de FastAPI.

### Requisito 5: Sistema de catálogo de tools

**Historia de usuario:** Como usuario del sistema, quiero un catálogo de herramientas disponibles, para que pueda descubrir y entender qué herramientas están disponibles y cómo usarlas.

**Criterios de aceptación:**

1. EL Tool_Catalog DEBERÁ mantener un registro de todas las MCP_Tools disponibles con metadatos.
2. CUANDO se registre una nueva herramienta, EL Tool_Catalog DEBERÁ almacenar su nombre, descripción, esquema de parámetros y categoría.
3. EL Tool_Catalog DEBERÁ admitir la categorización de herramientas (por ejemplo, «Integración de API», «Análisis de NLP», «Utilidades»).
4. AL consultar el catálogo, EL Tool_Catalog DEBERÁ devolver las herramientas filtradas por categoría si así se solicita.
5. EL Tool_Catalog DEBERÁ incluir esquemas de validación de parámetros para cada herramienta.
6. EL Tool_Catalog DEBERÁ admitir la búsqueda de herramientas por nombre o palabras clave de descripción.
7. EL Tool_Catalog DEBERÁ **agregar las herramientas de todos los MCP_Server conectados**, indicando de qué servidor procede cada una.
8. EL Tool_Catalog DEBERÁ construirse **dinámicamente** mediante el descubrimiento de herramientas de cada servidor (*handshake* MCP), sin listas cableadas en el código ni en el frontend.

### Requisito 6: Interfaz web

**Historia de usuario:** Como usuario final, quiero una interfaz web intuitiva, para que pueda gestionar y ejecutar herramientas MCP sin necesidad de usar la línea de comandos.

**Criterios de aceptación:**

1. LA Web_Interface DEBERÁ implementarse utilizando Angular y TypeScript.
2. LA Web_Interface DEBERÁ mostrar una lista de herramientas disponibles del catálogo de herramientas.
3. CUANDO un usuario seleccione una herramienta, LA Web_Interface DEBERÁ mostrar un formulario con los parámetros necesarios.
4. CUANDO un usuario envíe la ejecución de una herramienta, LA Web_Interface DEBERÁ enviar la solicitud a la Backend_API y mostrar los resultados.
5. LA Web_Interface DEBERÁ mostrar el historial de ejecución con marcas de tiempo y resultados.
6. LA Web_Interface DEBERÁ proporcionar información visual durante la ejecución de la herramienta (estados de carga).
7. LA Web_Interface DEBERÁ mostrar mensajes de error en un formato entendible.
8. LA Web_Interface DEBERÁ ser receptiva y funcionar en dispositivos de escritorio y tabletas.
9. LA Web_Interface DEBERÁ incluir capacidades de filtrado y búsqueda para el catálogo de herramientas.
10. LA Web_Interface DEBERÁ ofrecer **dos vías de entrada**: un formulario de análisis directo (determinista) y un **asistente conversacional** (ver Requisito 13).
11. LA Web_Interface DEBERÁ mostrar el estado de los **MCP_Server conectados** (nombre, transporte, estado y herramientas que aporta), generado dinámicamente a partir del descubrimiento; los filtros por servidor DEBERÁN derivarse de esa misma lista.
12. CUANDO el Agent_Orchestrator invoque herramientas, LA Web_Interface DEBERÁ renderizar el **resultado estructurado de cada herramienta** —no solo la narración del modelo— junto a la **traza** de herramientas invocadas.
13. SI la narración del modelo llega **vacía o ilegible**, ENTONCES LA Web_Interface DEBERÁ mostrar igualmente los **resultados estructurados** de las herramientas invocadas, indicando de forma discreta que el asistente no generó un resumen. LA Web_Interface NO DEBERÁ condicionar la visualización del análisis a la existencia de esa narración. _(Modo de fallo observado en el spike #82: el agente invoca correctamente las herramientas y devuelve una respuesta de cero caracteres; el análisis existe y no debe perderse.)_

### Requisito 7: Entorno de implementación de Docker

**Historia de usuario:** Como desarrollador del sistema, quiero un entorno de despliegue basado en Docker, para que el sistema sea fácil de instalar y ejecutar en diferentes entornos.

**Criterios de aceptación:**

1. EL Docker_Environment DEBERÁ utilizar Docker Compose para coordinar todos los servicios.
2. EL Docker_Environment DEBERÁ incluir un contenedor para Backend_API y MCP_Server.
3. EL Docker_Environment DEBERÁ incluir un contenedor para la Web_Interface.
4. CUANDO se inicia Docker Compose, EL Docker_Environment DEBERÁ inicializar todos los servicios en el orden correcto.
5. EL Docker_Environment DEBERÁ configurar adecuadamente la red entre contenedores.
6. EL Docker_Environment DEBERÁ montar volúmenes para el almacenamiento persistente de datos.
7. EL Docker_Environment DEBERÁ exponer los puertos adecuados para el acceso externo.
8. EL Docker_Environment DEBERÁ incluir la configuración de variables de entorno para diferentes escenarios de implementación.

### Requisito 8: Pipeline de integración continua y despliegue continuo

**Historia de usuario:** Como desarrollador del sistema, quiero un pipeline de CI/CD automatizado, para que el código sea validado y desplegado automáticamente.

**Criterios de aceptación:**

1. EL CI_Pipeline DEBERÁ implementarse utilizando GitHub Actions.
2. CUANDO se envía el código al repositorio, EL CI_Pipeline DEBERÁ ejecutar pruebas automatizadas.
3. DONDE se considere beneficioso, EL CI_Pipeline PODRÁ realizar comprobaciones de linting y calidad del código en Python y JavaScript.
4. EL CI_Pipeline DEBERÁ crear imágenes Docker tanto para el backend como para el frontend.
5. CUANDO las pruebas se superen, EL CI_Pipeline DEBERÁ etiquetar las compilaciones correctas.
6. EL CI_Pipeline DEBERÁ incluir flujos de trabajo separados para pull requests y commits de la rama main.
7. SI falla algún paso, ENTONCES EL CI_Pipeline DEBERÁ informar del fallo con registros detallados.

### Requisito 9: Persistencia de datos e historial

**Historia de usuario:** Como usuario del sistema, quiero que el historial de ejecuciones se guarde, para que pueda revisar resultados anteriores y analizar patrones de uso.

**Criterios de aceptación:**

1. LA Backend_API DEBERÁ conservar los registros de ejecución de herramientas en una base de datos o un almacenamiento de archivos.
2. CUANDO se ejecute una herramienta, LA Backend_API DEBERÁ almacenar el nombre de la herramienta, los parámetros, el resultado, la marca de tiempo y el estado de ejecución.
3. LA Backend_API DEBERÁ proporcionar un endpoint para recuperar el historial de ejecución con paginación.
4. LA Backend_API DEBERÁ admitir el filtrado del historial de ejecución por nombre de herramienta, intervalo de fechas y estado.
5. LA Backend_API DEBERÁ limitar el almacenamiento del historial para evitar un crecimiento ilimitado (por ejemplo, conservar las últimas 1000 ejecuciones o 30 días).
6. AL consultar el historial, LA Backend_API DEBERÁ devolver los resultados en orden cronológico inverso.

### Requisito 10: Gestión de errores y registro de eventos

**Historia de usuario:** Como desarrollador del sistema, quiero un sistema robusto de manejo de errores y logging, para que pueda diagnosticar problemas y mantener el sistema.

**Criterios de aceptación:**

1. EL MCP_Server DEBERÁ registrar todas las invocaciones de herramientas con marcas de tiempo y parámetros.
2. CUANDO se produzca un error, EL MCP_Server DEBERÁ registrar todos los detalles del error, incluyendo los stack traces.
3. LA Backend_API DEBERÁ implementar un logger estructurado con diferentes niveles de registro (DEBUG, INFO, WARNING, ERROR).
4. LA Backend_API DEBERÁ registrar todas las solicitudes HTTP entrantes con el método, la ruta y el estado de la respuesta.
5. DONDE sea posible, EL Docker_Environment PODRÁ configurar la visualización centralizada de logs de todos los contenedores.
6. LA Backend_API DEBERÁ incluir endpoints de chequeo de salud (health check) para monitorización.
7. CUANDO se produzcan errores críticos, LA Backend_API DEBERÁ garantizar que se registren antes de que la aplicación finalice.

### Requisito 11: Gestión de la configuración

**Historia de usuario:** Como administrador del sistema, quiero gestionar la configuración de forma centralizada, para que pueda adaptar el sistema a diferentes entornos sin modificar código.

**Criterios de aceptación:**

1. LA Backend_API DEBERÁ cargar la configuración desde las variables de entorno.
2. LA Backend_API DEBERÁ admitir archivos de configuración para claves API, endpoints y ajustes de servicio.
3. LA Backend_API DEBERÁ validar la configuración requerida al iniciarse y fallar rápidamente si falta.
4. EL Docker_Environment DEBERÁ utilizar archivos `.env` para la configuración específica del entorno.
5. LA Backend_API NO DEBERÁ exponer valores de configuración confidenciales en registros o respuestas de API.
6. CUANDO existan diferentes entornos de implementación, LA Backend_API DEBERÁ admitir modificaciones de configuración específicas para cada entorno.

### Requisito 12: Seguridad y validación de API

**Historia de usuario:** Como desarrollador del sistema, quiero que las APIs sean seguras y validen entradas, para que el sistema sea robusto contra entradas maliciosas o incorrectas.

**Criterios de aceptación:**

1. LA Backend_API DEBERÁ validar todos los parámetros de entrada utilizando mecanismos de validación apropiados (como Pydantic u otros).
2. CUANDO se reciba una entrada no válida, LA Backend_API DEBERÁ devolver un error `400 Bad Request` con los detalles del error de validación.
3. LA Backend_API DEBERÁ sanitizar las entradas de los usuarios para evitar ataques de inyección.
4. LA Backend_API DEBERÁ implementar una limitación de velocidad para evitar abusos.
5. LA Backend_API DEBERÁ incluir límites de tamaño de solicitud para evitar el agotamiento de los recursos.
6. LA Backend_API DEBERÁ validar las claves API para las llamadas a servicios externos antes de realizar solicitudes.
7. LA Backend_API NO DEBERÁ revelar detalles de errores internos a clientes externos en modo de producción.

### Requisito 13: Agente conversacional (orquestador LLM)

**Historia de usuario:** Como usuario final, quiero consultar en lenguaje natural, para que el sistema decida por mí qué herramientas usar sin necesidad de conocer el catálogo.

**Criterios de aceptación:**

1. EL Agent_Orchestrator DEBERÁ interpretar consultas en lenguaje natural e invocar dinámicamente las MCP_Tools necesarias (*tool calling*).
2. EL Agent_Orchestrator DEBERÁ obtener las herramientas disponibles mediante el **descubrimiento MCP** (actuando como cliente), sin integraciones específicas por herramienta: añadir una herramienta nueva NO DEBERÁ requerir tocar el agente.
3. EL Agent_Orchestrator DEBERÁ devolver, junto a su respuesta en lenguaje natural, la **traza** de herramientas invocadas y el **resultado estructurado** de cada una.
4. EL veredicto de clickbait NO DEBERÁ emitirlo el modelo de lenguaje: DEBERÁ proceder de las MCP_Tools, limitándose el modelo a narrar y contrastar. _(Salvaguarda de R3.8: la explicabilidad no puede depender de un modelo opaco.)_
5. EL **prompt de sistema** DEBERÁ ser un artefacto de configuración **versionado y consultable**, no código embebido. _(R3.9: transparencia de sistema.)_
6. EL LLM_Backend DEBERÁ ser **intercambiable por configuración** (local vía Ollama o API externa), siguiendo el patrón ya usado para `nlp_backend`. _(R3.9.)_
7. EL Agent_Orchestrator DEBERÁ disponer de su propia **ficha de modelo**, declarando su naturaleza opaca y sus limitaciones conocidas. _(R3.9.)_
8. SI el modelo no soporta *tool calling* de forma fiable, ENTONCES el sistema PODRÁ operar en **modo guiado**: la selección de herramientas la decide el backend de forma determinista y el modelo solo narra. _(Degradación prevista para modelos locales pequeños.)_
