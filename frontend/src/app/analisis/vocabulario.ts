import type { DimensionVerdict, SignalResult } from '../api/models';

// En caja normal a propósito: las mayúsculas las pone el CSS. Muchos lectores
// de pantalla deletrean las palabras escritas en caja alta.
const VEREDICTOS: Record<string, string> = {
  deceptive: 'Engañoso',
  stylistic_clickbait: 'Clickbait de forma',
  factual: 'Factual',
  ambiguous: 'Ambiguo',
  no_data: 'Sin datos',
};

/** Las siete categorías de pista de `lexical.py`. */
const CATEGORIAS: Record<string, string> = {
  hyperbole: 'hipérbole',
  forward_reference: 'referencia vaga',
  curiosity_gap: 'brecha de curiosidad',
  leading_number: 'número inicial',
  question: 'pregunta',
  all_caps: 'mayúsculas',
  ellipsis: 'puntos suspensivos',
};

const DIMENSIONES: Record<string, string> = {
  form: 'Forma',
  deception: 'Engaño',
  tone: 'Tono',
};

/**
 * La etiqueta legible de una señal, o su id de máquina si no la trae.
 *
 * Hasta #133 aquí vivía un diccionario `tool → nombre` que duplicaba el campo
 * `name` de las fichas del backend **sin ninguna vigilancia**: renombrar una
 * señal allí no rompía ningún test, sólo hacía que la pantalla pintara el id
 * crudo. Ahora el nombre viaja en la respuesta y este fichero no se lo inventa.
 *
 * El `??` se queda, pero tapa otra cosa: ya no un diccionario incompleto sino
 * una respuesta ANTIGUA, de antes de que `label` existiera, recuperada del
 * historial. Fea, pero visible — que es la regla de toda esta interfaz.
 */
export function nombreDeSenal(senal: SignalResult): string {
  return senal.label ?? senal.name;
}

export function nombreDeVeredicto(verdict: string): string {
  return VEREDICTOS[verdict] ?? verdict;
}

export function nombreDeDimension(dimension: string): string {
  return DIMENSIONES[dimension] ?? dimension;
}

export function nombreDeCategoria(categoria: string): string {
  return CATEGORIAS[categoria] ?? categoria;
}

/** Qué dijo la señal, o por qué no dijo nada. */
export function estadoDeSenal(senal: SignalResult): string {
  if (senal.status === 'not_applicable') return 'no aplicable';
  if (senal.status === 'error') return 'error';
  // `== null` cubre null Y undefined: el campo es opcional en el contrato, y
  // con `=== null` una señal sin él se pintaría como «no clickbait».
  if (senal.is_clickbait == null) return 'no vota';
  return senal.is_clickbait ? 'clickbait' : 'no clickbait';
}

/** Decimales con coma. `DecimalPipe` daría «0.99» sin registrar el locale. */
export function numero(valor: number, decimales = 2): string {
  return valor.toLocaleString('es-ES', {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
}

/** Tres casos, no dos: el `null` ES el resultado, no un hueco. */
export function resumenDimension(veredicto: DimensionVerdict): string {
  if (veredicto.is_clickbait == null) return 'las señales discrepan';
  return veredicto.is_clickbait ? 'sí' : 'no';
}
