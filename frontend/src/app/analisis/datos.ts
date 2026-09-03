/**
 * Las formas que tiene el `data` crudo de cada señal.
 *
 * El contrato lo declara como diccionario libre (`dict[str, Any]`) para no
 * perder información, así que la interfaz tiene que decir qué espera. Y en vez
 * de castear —que mentiría en silencio el día que el backend cambie— cada
 * función COMPRUEBA y devuelve `null` si la forma no encaja: la tarjeta degrada
 * a JSON crudo en lugar de pintar `undefined`.
 */

/** Una marca léxica y dónde aparece en el titular. */
export interface Pista {
  category: string;
  cue: string;
  span: [number, number];
}

export interface DatosLexico {
  score: number;
  matches: Pista[];
}

export function comoLexico(crudo: unknown): DatosLexico | null {
  const datos = crudo as DatosLexico | null;
  if (!datos || typeof datos.score !== 'number' || !Array.isArray(datos.matches)) {
    return null;
  }

  // `?.` porque el array puede traer nulos: un guardián que revienta es peor
  // que no tener guardián. Y `Array.isArray` porque `typeof []` es 'object'.
  const validas = datos.matches.every(
    (pista) =>
      typeof pista?.cue === 'string' &&
      Array.isArray(pista?.span) &&
      pista.span.length === 2,
  );
  return validas ? datos : null;
}
