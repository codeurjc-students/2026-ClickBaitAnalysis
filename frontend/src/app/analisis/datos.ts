/**
 * Las formas que tiene el `data` crudo de cada señal.
 *
 * El contrato lo declara como diccionario libre (`dict[str, Any]`) para no
 * perder información, así que la interfaz tiene que decir qué espera. Y en vez
 * de castear —que mentiría en silencio el día que el backend cambie— cada
 * función COMPRUEBA y devuelve `null` si la forma no encaja: la tarjeta degrada
 * a JSON crudo en lugar de pintar `undefined`.
 *
 * Desde #133 las formas **se derivan del contrato generado** en vez de
 * escribirse aquí. Eran las mismas cuatro declaradas dos veces —en `outputs.py`
 * y en este fichero— sin ningún vínculo entre ellas, así que renombrar un campo
 * en el backend no rompía nada: el guardián empezaba a devolver `null` y la
 * tarjeta degradaba a JSON crudo, en silencio y para siempre.
 *
 * Se usa `Pick` y no el tipo entero **a propósito**: cada guardián comprueba
 * unos campos concretos, y devolver el tipo completo afirmaría que existen
 * otros que nadie ha mirado. Así el tipo dice exactamente lo verificado — y si
 * el backend renombra uno de esos campos, esto deja de compilar.
 */
import type {
  Etiqueta,
  Pista,
  SalidaIncoherencia,
  SalidaLexica,
  SalidaLineal,
} from '../api/models';

/** Una marca léxica y dónde aparece en el titular. */
export type { Pista };

export type DatosLexico = Pick<SalidaLexica, 'score' | 'matches'>;

export type DatosLineal = Pick<SalidaLineal, 'probability' | 'top_cues'>;

export type DatosIncoherencia = Pick<
  SalidaIncoherencia,
  'similarity' | 'incoherent'
> & {
  /**
   * Opcional aunque el contrato lo declare obligatorio, y no por las filas ya
   * guardadas: `data` es libre para que quepan señales que todavía no existen,
   * y una señal futura puede perfectamente no decidir por umbral.
   */
  threshold?: SalidaIncoherencia['threshold'];
};

export type DatosEtiqueta = Etiqueta;

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

export function comoLineal(crudo: unknown): DatosLineal | null {
  const datos = crudo as DatosLineal | null;
  if (!datos || typeof datos.probability !== 'number') return null;
  return Array.isArray(datos.top_cues) ? datos : null;
}

export function comoIncoherencia(crudo: unknown): DatosIncoherencia | null {
  const datos = crudo as DatosIncoherencia | null;
  return datos && typeof datos.similarity === 'number' ? datos : null;
}

/** Sirve a las dos señales que devuelven `{label, score}`, y a las futuras. */
export function comoEtiqueta(crudo: unknown): DatosEtiqueta | null {
  const datos = crudo as DatosEtiqueta | null;
  if (!datos || typeof datos.label !== 'string') return null;
  return typeof datos.score === 'number' ? datos : null;
}
