import type { DimensionGuardada, SenalGuardada } from './formas';

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
export function nombreDeSenal(senal: SenalGuardada): string {
  return senal.label ?? senal.name;
}

/**
 * El nombre de una señal para el ÍNDICE, sin su precisión entre paréntesis.
 *
 * Los `label` que llegan desde #133 la traen incorporada —«RoBERTa dedicado
 * (entrenado en Webis-17)»—, y eso es justo lo que hace falta en la ficha y
 * estorba en un índice: medido en #130, una sola pastilla ocupaba 531 px de
 * 1024, y la plantilla seguía prometiendo que cabían todas sobre la línea de
 * flotación.
 *
 * Se corta por el paréntesis, que es una REGLA y no un diccionario: una señal
 * nueva no hay que añadirla aquí. El nombre completo sigue entero en la
 * tarjeta, que es donde se lee con calma.
 */
export function nombreCortoDeSenal(senal: SenalGuardada): string {
  return nombreDeSenal(senal).split(' (')[0];
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

/**
 * ¿Llegó esta señal a producir un resultado?
 *
 * Se compara contra `ok` y no contra la lista de estados malos a propósito:
 * `not_applicable` se llamaba `no_aplicable` antes de #134, así que enumerar
 * los fallos dejaría sin apagar lo guardado entonces. `ok` es el valor que no
 * ha cambiado nunca.
 */
export function funciono(senal: SenalGuardada): boolean {
  return senal.status === 'ok';
}

/** Qué dijo la señal, o por qué no dijo nada. */
export function estadoDeSenal(senal: SenalGuardada): string {
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
export function resumenDimension(veredicto: DimensionGuardada): string {
  if (veredicto.is_clickbait == null) return 'las señales discrepan';
  return veredicto.is_clickbait ? 'sí' : 'no';
}
