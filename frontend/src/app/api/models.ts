/**
 * Nombres cortos para los tipos del contrato.
 *
 * `schema.d.ts` es generado y los publica anidados, así que sin este fichero
 * cada componente escribiría `components['schemas']['AnalyzeResponse']`.
 *
 * Son ALIAS, no copias: si un esquema desaparece o se renombra en el backend,
 * el fallo salta aquí —en una línea, al compilar— y no en la plantilla que lo
 * usaba. Esa es la razón de mantener la lista a mano en vez de reexportar
 * `components` entero.
 */
import type { components, paths } from './schema';

type Esquemas = components['schemas'];

// --- Análisis de un titular (POST /analyze) ---
//
// Lo que entra y sale de una RUTA se toma de `paths`, no de `components`, y esa
// diferencia es la salvaguarda de la costura menos protegida de la cadena.
//
// El servicio hace `http.post<T>(...)`, y ese genérico no comprueba nada: es una
// afirmación sobre lo que va a llegar. Eligiendo `T` a mano de `components`,
// nada ata el tipo a la ruta — y en #133 pasó exactamente eso: el backend empezó
// a devolver el sobre y el frontend siguió compilando con el tipo viejo puesto,
// porque `AnalyzeResponse` seguía existiendo como esquema.
//
// Derivándolo de `paths`, cambiar lo que devuelve `/analyze` cambia este tipo al
// regenerar, y rompe a quien supusiera la forma anterior. La elección deja de
// ser de quien escribe el servicio y pasa a ser del contrato.
//
// Sigue sin cubrir que el backend DESPLEGADO no corresponda al contrato
// commiteado; para eso haría falta validar en ejecución.
type Analyze = paths['/analyze']['post'];

export type AnalyzeRequest = Analyze['requestBody']['content']['application/json'];
// El sobre de la respuesta: el análisis más el id con el que quedó registrado.
// Lo que se pinta es `AnalyzeResponse`; el id sólo sirve para volver a él.
export type AnalyzeResult =
  Analyze['responses'][200]['content']['application/json'];

// `AnalyzeResponse` sigue viniendo de `components` a propósito: es un esquema por
// derecho propio, no lo que devuelve una ruta. El historial lo guarda y #129 lo
// leerá desde ahí, sin pasar por `/analyze`.
export type AnalyzeResponse = Esquemas['AnalyzeResponse'];
export type SignalResult = Esquemas['SignalResult'];
export type DimensionVerdict = Esquemas['DimensionVerdict'];

// --- Formas conocidas del `data` de cada señal ---
//
// `data` es un diccionario libre en el contrato, así que estos tipos NO se
// aplican solos: hay que comprobar en ejecución, y de eso se encargan los
// guardianes de `analisis/datos.ts`. Lo que aportan es que esos guardianes
// validen contra una forma DERIVADA del backend en vez de contra una copia
// escrita a mano, que es lo que había hasta #133.
export type SalidaLexica = Esquemas['SalidaLexica'];
export type SalidaLineal = Esquemas['SalidaLineal'];
export type SalidaIncoherencia = Esquemas['SalidaIncoherencia'];
export type Etiqueta = Esquemas['Etiqueta'];
export type Pista = Esquemas['Pista'];

// Uniones de cadenas, no `enum` de TypeScript: al ser estructurales, comparar
// contra un valor que no existe —`'engaño'` con eñe— no compila.
export type Dimension = Esquemas['Dimension'];
export type OverallVerdict = Esquemas['OverallVerdict'];
export type SignalStatus = Esquemas['SignalStatus'];
export type SignalType = Esquemas['SignalType'];

// --- Catálogo de herramientas (GET /tools) ---
//
// Lo que devuelve la RUTA sale de `paths`, igual que en `/analyze`.
// `CatalogResponse` existe como esquema y hoy coincide, pero nombrarlo a mano
// volvería a dejar la respuesta sin atar a la ruta.
type Tools = paths['/tools']['get'];
export type CatalogResult = Tools['responses'][200]['content']['application/json'];

// Las piezas de dentro sí vienen de `components`: son esquemas por derecho
// propio, y llegan sueltas a los componentes que las pintan.
export type ServerInfo = Esquemas['ServerInfo'];
export type ServerStatus = Esquemas['ServerStatus'];
export type ToolInfo = Esquemas['ToolInfo'];
export type ToolModelCard = Esquemas['ToolModelCard'];

// --- Ejecución de una herramienta (POST /tools/{name}/execute) ---
//
// La clave de `paths` es la PLANTILLA literal, con `{name}` dentro, y no la URL
// ya sustituida: lo que está en el contrato es la ruta, no cada invocación.
type Execute = paths['/tools/{name}/execute']['post'];
export type ExecuteBody = Execute['requestBody']['content']['application/json'];
export type ExecuteResult = Execute['responses'][200]['content']['application/json'];

// Los argumentos son un diccionario libre —cada herramienta tiene los suyos, y
// la forma buena la publica su `input_schema`—, así que se comprueban en
// ejecución como el `data` de una señal. Se deriva en vez de escribirlo a mano
// para que un cambio del contrato llegue hasta aquí, y `NonNullable` porque la
// clave es opcional en el contrato pero el servicio siempre la manda.
export type Argumentos = NonNullable<ExecuteBody['arguments']>;

export type ExecuteStatus = Esquemas['ExecuteStatus'];

// --- Historial (GET /history) ---
export type HistoryPage = Esquemas['HistoryPage'];
export type HistoryEntry = Esquemas['HistoryEntry'];
export type HistoryKind = Esquemas['HistoryKind'];
export type Origin = Esquemas['Origin'];
export type RetentionPolicy = Esquemas['RetentionPolicy'];

// --- Errores de validación de FastAPI (422) ---
export type HTTPValidationError = Esquemas['HTTPValidationError'];
export type ValidationError = Esquemas['ValidationError'];
