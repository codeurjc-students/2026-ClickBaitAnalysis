import { HttpErrorResponse } from '@angular/common/http';

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
    // FastAPI responde {"detail": [{"loc", "msg", "type"}]}, pero `error` es
    // `any`: un proxy puede colar una página HTML. De ahí el encadenamiento.
    const detalle = fallo.error?.detail?.[0]?.msg;
    return detalle
      ? `La petición no es válida: ${detalle}`
      : 'La petición no es válida.';
  }
  if (fallo.status >= 500) {
    return `La API falló al analizar (${fallo.status}). Vuelve a intentarlo.`;
  }
  return `No se pudo analizar el titular (${fallo.status}).`;
}
