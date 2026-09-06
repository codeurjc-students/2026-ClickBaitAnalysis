import { HttpErrorResponse } from '@angular/common/http';

import { detalleDeValidacion, SIN_RESPUESTA } from '../api/errores';

/**
 * Traduce el fallo a algo que se pueda leer (R6.7).
 *
 * Los mensajes son de ESTA pantalla: hablan de analizar un titular. Lo que se
 * lee del cuerpo, y el caso de que no conteste nadie, viven en `api/errores.ts`
 * porque los comparte con el catálogo, que dice otras cosas de lo mismo.
 */
export function mensajeDeError(fallo: HttpErrorResponse): string {
  if (fallo.status === 0) return SIN_RESPUESTA;
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
