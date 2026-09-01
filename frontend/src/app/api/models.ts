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
export type AnalyzeResponse = Esquemas['AnalyzeResponse'];
export type SignalResult = Esquemas['SignalResult'];
export type DimensionVerdict = Esquemas['DimensionVerdict'];

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
