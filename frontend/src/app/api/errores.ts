/**
 * Lo que se puede leer del cuerpo de un error HTTP.
 *
 * Vive en `api/` y no en una pantalla porque no es de ninguna: es la forma en
 * que FastAPI cuenta qué no le encaja, y la usan el análisis (titular en
 * blanco) y el catálogo (argumentos que no cumplen el `input_schema`) para
 * decir cosas distintas. El MENSAJE es de cada pantalla; leer el cuerpo, no.
 */

/**
 * El primer mensaje de un 422 de FastAPI, si el cuerpo tiene esa forma.
 *
 * FastAPI responde `{"detail": [{"loc", "msg", "type"}]}`, pero `fallo.error`
 * es `any` y **un proxy puede colar una página HTML por ahí**. Antes se
 * encadenaba con `?.` sobre ese `any`, que funciona pero apaga el tipado: el
 * resultado también era `any`, y a partir de ahí nada se comprobaba.
 *
 * Se comprueba en vez de castear, que es la regla de esta interfaz — la misma
 * que gobierna los guardianes del `data` en `analisis/datos.ts`. Lo destapó
 * ESLint con información de tipos (#140), como `no-unsafe-member-access`.
 */
export function detalleDeValidacion(cuerpo: unknown): string | null {
  if (typeof cuerpo !== 'object' || cuerpo === null) return null;

  const { detail } = cuerpo as { detail?: unknown };
  if (!Array.isArray(detail) || detail.length === 0) return null;

  const primero = detail[0] as { msg?: unknown };
  return typeof primero?.msg === 'string' ? primero.msg : null;
}

/**
 * Mensaje de lo que no depende de la pantalla: la petición no salió, o no
 * contestó nadie.
 *
 * `status 0` no es un código HTTP. Separarlo importa porque el remedio que le
 * das a quien mira es otro: no es un fallo del análisis ni del catálogo, es que
 * no hay API al otro lado.
 */
export const SIN_RESPUESTA =
  'No se pudo contactar con la API.';
