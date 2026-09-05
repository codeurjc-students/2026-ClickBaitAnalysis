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
import type { components } from './schema';

type Esquemas = components['schemas'];

// --- Análisis de un titular (POST /analyze) ---
export type AnalyzeRequest = Esquemas['AnalyzeRequest'];
// El sobre de la respuesta: el análisis más el id con el que quedó registrado.
// Lo que se pinta es `AnalyzeResponse`; el id sólo sirve para volver a él.
export type AnalyzeResult = Esquemas['AnalyzeResult'];
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
export type CatalogResponse = Esquemas['CatalogResponse'];
export type ServerInfo = Esquemas['ServerInfo'];
export type ServerStatus = Esquemas['ServerStatus'];
export type ToolInfo = Esquemas['ToolInfo'];
export type ToolModelCard = Esquemas['ToolModelCard'];
export type Origin = Esquemas['Origin'];

// --- Ejecución directa de una herramienta (POST /execute) ---
export type ExecuteRequest = Esquemas['ExecuteRequest'];
export type ExecuteResponse = Esquemas['ExecuteResponse'];
export type ExecuteStatus = Esquemas['ExecuteStatus'];

// --- Historial (GET /history) ---
export type HistoryPage = Esquemas['HistoryPage'];
export type HistoryEntry = Esquemas['HistoryEntry'];
export type HistoryKind = Esquemas['HistoryKind'];
export type RetentionPolicy = Esquemas['RetentionPolicy'];

// --- Errores de validación de FastAPI (422) ---
export type HTTPValidationError = Esquemas['HTTPValidationError'];
export type ValidationError = Esquemas['ValidationError'];
