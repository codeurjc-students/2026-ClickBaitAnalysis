/**
 * Qué se puede leer del `payload` de una entrada del historial.
 *
 * El contrato lo declara diccionario libre, y con razón: guarda **la respuesta
 * completa de cuando se ejecutó**, incluidas las de versiones anteriores del
 * sistema. Por eso `as AnalyzeResponse` sobre el payload está descartado por
 * decisión escrita: sería una afirmación sobre datos que se guardaron cuando el
 * contrato era otro.
 *
 * Se comprueba, como hace `analisis/datos.ts` con el `data` de cada señal, y si
 * no encaja se devuelve `null` para que la pantalla enseñe el JSON crudo.
 *
 * **Los tipos de aquí son más anchos que los del contrato a propósito**, y ésa
 * es la parte que importa: `required` en el contrato significa «lo que el
 * backend produce HOY», y el historial guarda lo de ayer. Dos casos ya
 * ocurridos en este repositorio:
 *
 * - `label` es obligatorio en `SignalResult` **desde #133**. Lo guardado antes
 *   no lo trae, así que exigirlo mandaría a JSON crudo todas las entradas
 *   anteriores al 5 de septiembre. `nombreDeSenal` ya cae a `name` para este
 *   caso exacto, y su comentario lo dice.
 * - `verdict`, `status`, `type` y `dimension` son enums cerrados hoy, pero
 *   **#134 cambió sus valores** de castellano con diacríticos a inglés. Una
 *   entrada vieja dice `engañoso` donde el contrato dice `deceptive`. Aquí se
 *   piden cadenas, no miembros del enum: el vocabulario ya cae al valor crudo
 *   cuando no lo conoce, y ver `engañoso` es mejor que no ver el análisis.
 *
 * `AnalyzeResponse` es asignable a `AnalisisGuardado` —un enum encaja en
 * `string`—, así que la misma vista sirve para un análisis recién hecho y para
 * uno recuperado. Al revés no, y es lo correcto: lo de aquí no puede pasar por
 * donde se espera el contrato de hoy.
 */

/** Una señal tal como puede llegar del historial. */
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

/** Una dimensión tal como puede llegar del historial. */
export interface DimensionGuardada {
  dimension: string;
  is_clickbait?: boolean | null;
  contributing?: string[] | null;
}

/** Un análisis recuperado del historial. */
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
 * El payload como análisis, o `null` si no lo es.
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
