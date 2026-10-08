/**
 * Las formas de un análisis que las piezas de `senales/` saben pintar.
 *
 * Son más anchas que las del contrato a propósito, porque lo que se pinta
 * llega de DOS orígenes: el análisis recién hecho, que llega con el contrato de
 * hoy, y el recuperado del historial, que se guardó cuando el contrato era
 * otro. Viven junto a quien las dibuja, y fuera de cualquier pantalla: en una
 * pantalla, las demás tendrían que depender de ella para dibujar una señal
 * (tensión 5 de `docs/estructura.md`, resuelta en #190).
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
 * - **`language` puede faltar.** El contrato lo trae desde #229; lo guardado
 *   antes no, y entonces el contrato decía que el titular era inglés. Lo
 *   resuelve `idiomaDelTitular`, y en una ejecución suelta, cuya salida lo
 *   trae desde #230, `idiomaDeLaEjecucion`.
 *
 * Aquí vive además `comoAnalisis`, el guardián que lee un análisis de datos sin
 * tipo. Va junto a las formas porque lo necesita quien pinta un análisis que
 * no llega tipado: el guardado en el historial (#129) y, desde el asistente,
 * el que devuelve `analyze_headline` dentro de la traza (#191).
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
  /** El idioma con el que se analizó (#229). Falta en lo guardado antes. */
  language?: string | null;
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

/**
 * El idioma del titular, para su atributo `lang` (#229).
 *
 * Es el que guardó el análisis —con el que decidió qué señales ejecutar—, no
 * uno recalculado aquí: detectarlo en el navegador sería una segunda copia del
 * detector (#116). Lo guardado antes de #229 no lo trae, y entonces el contrato
 * decía que el titular era inglés. `und` se devuelve tal cual: en BCP 47 es
 * «indeterminado», que es lo que hay que decirle a un lector de pantalla.
 *
 * Mira el tipo aunque el campo se declare cadena: `comoAnalisis` no lo
 * comprueba, porque un valor raro no debe esconder el análisis entero.
 */
export function idiomaDelTitular(analisis: AnalisisGuardado | null): string {
  const idioma = analisis?.language;
  return typeof idioma === 'string' ? idioma : 'en';
}

/**
 * El idioma en que una herramienta suelta analizó su titular (#230), para su
 * `lang` en el historial.
 *
 * Una ejecución guarda su `ExecuteResponse` entera, y desde #230 la salida de
 * cada señal dice su idioma en `data.language`, como un análisis lo dice en
 * `language`. Una con salida pero sin él es de antes de #230, cuando todo se
 * analizaba en inglés: queda en «en».
 *
 * Una SIN salida —rechazada o fallida— no dice nada del idioma, y el caso que
 * más pesa es justo el de un titular que no está en inglés: la señal se niega
 * y no devuelve nada. Dar «en» sería afirmar lo contrario de lo que pasó, así
 * que queda en `und`, «indeterminado» en BCP 47 (decidido en #230).
 */
export function idiomaDeLaEjecucion(crudo: unknown): string {
  const ejecucion = crudo as { data?: { language?: unknown } | null } | null;
  const datos = ejecucion?.data;
  if (!datos || typeof datos !== 'object') return 'und';
  return typeof datos.language === 'string' ? datos.language : 'en';
}
