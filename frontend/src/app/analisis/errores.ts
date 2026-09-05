import { HttpErrorResponse } from '@angular/common/http';

/**
 * El primer mensaje de un 422 de FastAPI, si el cuerpo tiene esa forma.
 *
 * FastAPI responde `{"detail": [{"loc", "msg", "type"}]}`, pero `fallo.error`
 * es `any` y **un proxy puede colar una página HTML por ahí**. Antes se
 * encadenaba con `?.` sobre ese `any`, que funciona pero apaga el tipado: el
 * resultado también era `any`, y a partir de ahí nada se comprobaba.
 *
 * Se comprueba en vez de castear, que es la regla de esta interfaz — la misma
 * que gobierna los guardianes del `data` en `datos.ts`. Lo destapó ESLint con
 * información de tipos (#140), como `no-unsafe-member-access`.
 */
function detalleDeValidacion(cuerpo: unknown): string | null {
  if (typeof cuerpo !== 'object' || cuerpo === null) return null;

  const { detail } = cuerpo as { detail?: unknown };
  if (!Array.isArray(detail) || detail.length === 0) return null;

  const primero = detail[0] as { msg?: unknown };
  return typeof primero?.msg === 'string' ? primero.msg : null;
}

/**
 * Traduce el fallo a algo que se pueda leer (R6.7).
 *
 * `status 0` no es un código HTTP: la petición no llegó a salir o no contestó
 * nadie. Separarlo importa porque el remedio que le das al usuario es otro.
 */
export function mensajeDeError(fallo: HttpErrorResponse): string {
  if (fallo.status === 0) {
    return 'No se pudo contactar con la API. Comprueba que está arrancada en el puerto 8000.';
  }
  if (fallo.status === 422) {
    const detalle = detalleDeValidacion(fallo.error);
    return detalle
      ? `La petición no es válida: ${detalle}`
      : 'La petición no es válida.';
  }
  if (fallo.status >= 500) {
    return `La API falló al analizar (${fallo.status}). Vuelve a intentarlo.`;
  }
  return `No se pudo analizar el titular (${fallo.status}).`;
}
