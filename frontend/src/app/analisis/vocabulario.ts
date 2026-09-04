import type { DimensionVerdict, SignalResult } from '../api/models';

/**
 * DUPLICA el campo `name` de MODEL_CARDS, que no viaja en la respuesta de
 * /analyze. Desaparece cuando #133 añada `label` a SignalResult.
 */
const NOMBRES: Record<string, string> = {
  detect_clickbait_lexical: 'Léxico (reglas)',
  detect_clickbait_linear: 'Modelo lineal',
  detect_clickbait_incoherence: 'Incoherencia titular ↔ cuerpo',
  detect_clickbait: 'RoBERTa dedicado',
  analyze_sentiment: 'Tono',
};

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

// El `??` es lo que hace que una señal desconocida se pinte con su id crudo en
// vez de con `undefined`: fea, pero visible.
export function nombreDeSenal(senal: SignalResult): string {
  return NOMBRES[senal.name] ?? senal.name;
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
