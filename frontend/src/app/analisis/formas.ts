/**
 * Las formas que la vista de análisis sabe pintar.
 *
 * Son más anchas que las del contrato a propósito, y viven aquí —junto a quien
 * las dibuja— porque esta vista sirve a DOS orígenes: el análisis recién hecho,
 * que llega con el contrato de hoy, y el recuperado del historial, que se
 * guardó cuando el contrato era otro. Si vivieran en `historial/`, dibujar una
 * señal obligaría a `analisis/` a depender de esa pantalla.
 *
 * `AnalyzeResponse` es asignable a `AnalisisGuardado` —un enum encaja en
 * `string`—, y al revés no. Esa asimetría es la que hace correcto tener un solo
 * componente: lo estrecho pasa por donde se espera lo ancho, nunca al revés.
 *
 * Qué se ensancha, y por qué no es teórico:
 *
 * - **`label` puede faltar.** Es obligatorio en `SignalResult` desde #133; lo
 *   guardado antes no lo trae. `nombreDeSenal` ya cae a `name` por esto.
 * - **Los enums son cadenas aquí.** #134 cambió sus valores de castellano a
 *   inglés, y en la base local hay una entrada con `verdict: "ambiguo"`
 *   (comprobado). Rechazarla escondería el análisis entero por una etiqueta;
 *   el vocabulario cae al valor crudo y se lee lo que hay.
 *
 * Aquí vive además `comoAnalisis`, el guardián que lee un análisis de datos sin
 * tipo. Va junto a las formas y no en `historial/` porque quien lo necesita es
 * esta pantalla —la que pinta un análisis guardado—, y al revés `analisis/`
 * acabaría dependiendo de la pantalla del historial para dibujar una señal.
 */

/** Una señal, venga del análisis de ahora o del historial. */
export interface SenalGuardada {
  name: string;
  /** Falta en lo guardado antes de #133. */
  label?: string | null;
  status: string;
  dimension: string;
  type: string;
  is_clickbait?: boolean | null;
  data?: Record<string, unknown> | null;
  detail?: string | null;
}

/** Una dimensión, venga de donde venga. */
export interface DimensionGuardada {
  dimension: string;
  is_clickbait?: boolean | null;
  contributing?: string[] | null;
}

/** Un análisis completo: el de ahora o el que se recupera.  */
export interface AnalisisGuardado {
  headline: string;
  content?: string | null;
  signals: SenalGuardada[];
  dimensions: DimensionGuardada[];
  verdict: string;
}

// El `?.` no sobra: un array puede traer nulos, y un guardián que revienta es
// peor que no tener guardián.
function esSenal(senal: SenalGuardada | null): boolean {
  return (
    typeof senal?.name === 'string' &&
    typeof senal.status === 'string' &&
    typeof senal.dimension === 'string' &&
    typeof senal.type === 'string'
  );
}

function esDimension(dimension: DimensionGuardada | null): boolean {
  return typeof dimension?.dimension === 'string';
}

/**
 * Un análisis leído de datos sin tipo, o `null` si no lo son.
 *
 * Lo que entra es el `payload` de una entrada del historial: el contrato lo
 * declara diccionario libre —con razón, porque guarda **la respuesta completa
 * de cuando se ejecutó**, incluidas las de versiones anteriores—, así que
 * `as AnalyzeResponse` sobre él está descartado por decisión escrita: sería una
 * afirmación sobre datos guardados cuando el contrato era otro.
 *
 * Es el mismo trabajo que hacen los guardianes de `datos.ts` con el `data` de
 * una señal, un nivel más arriba.
 *
 * Devuelve `null` también para las entradas de tipo `tool`, que guardan un
 * `ExecuteResponse`. El historial mezcla las dos cosas, y comprobar la forma es
 * más fiable que fiarse del campo `kind`: éste dice lo que se pidió, aquélla lo
 * que de verdad se puede pintar.
 */
export function comoAnalisis(crudo: unknown): AnalisisGuardado | null {
  const analisis = crudo as AnalisisGuardado | null;
  if (!analisis || typeof analisis !== 'object') return null;

  if (typeof analisis.headline !== 'string') return null;
  if (typeof analisis.verdict !== 'string') return null;

  if (!Array.isArray(analisis.signals) || !analisis.signals.every(esSenal)) {
    return null;
  }
  if (
    !Array.isArray(analisis.dimensions) ||
    !analisis.dimensions.every(esDimension)
  ) {
    return null;
  }

  return analisis;
}
