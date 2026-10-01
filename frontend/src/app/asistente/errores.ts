import { HttpErrorResponse } from '@angular/common/http';

import { detalleDeValidacion, mensajeDeLimite, SIN_RESPUESTA } from '../api/errores';

/**
 * Traduce el fallo de una pregunta al asistente a algo que se pueda leer (R6.7).
 *
 * Los mensajes son de ESTA pantalla, como los de `analisis/errores.ts`: lo que
 * se lee del cuerpo, y el caso de que no conteste nadie, viven en
 * `api/errores.ts`.
 */
export function mensajeDelChat(fallo: HttpErrorResponse): string {
  if (fallo.status === 0) return SIN_RESPUESTA;
  if (fallo.status === 429) return mensajeDeLimite(fallo);
  if (fallo.status === 503) {
    // El backend ya redacta por qué: apagado, sin el modelo, o con la cola
    // llena. Es una frase para enseñar tal cual (#189).
    return (
      detalleDeTexto(fallo.error) ?? 'El asistente no está disponible ahora mismo.'
    );
  }
  if (fallo.status === 404) {
    // Las conversaciones viven en memoria: caducan, y se pierden si la API se
    // reinicia. No es una avería, y decirlo así evita buscar una.
    return 'La conversación ya no está en el servidor: caducó o el servidor se reinició. Vuelve a preguntar.';
  }
  if (fallo.status === 422) {
    const detalle = detalleDeValidacion(fallo.error);
    return detalle ? `La pregunta no es válida: ${detalle}` : 'La pregunta no es válida.';
  }
  return `El asistente no pudo responder (${fallo.status}). Vuelve a intentarlo.`;
}

/** El `detail` de un error cuando es una frase y no una lista de validación. */
function detalleDeTexto(cuerpo: unknown): string | null {
  if (typeof cuerpo !== 'object' || cuerpo === null) return null;
  const { detail } = cuerpo as { detail?: unknown };
  return typeof detail === 'string' ? detail : null;
}
