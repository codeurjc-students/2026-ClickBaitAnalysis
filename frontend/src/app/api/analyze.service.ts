/**
 * Cliente de `POST /analyze`.
 *
 * Vive en `api/` junto a `schema.d.ts` y `models.ts` porque es el tercer eslabón
 * de la misma cadena: el backend publica el contrato, `openapi-typescript` lo
 * convierte en tipos y esto es lo único que sabe pedirlo. Un componente que
 * quiera analizar un titular inyecta esto, nunca `HttpClient` a pelo — así la
 * ruta y la forma del cuerpo viven en un solo sitio.
 */
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import type { AnalyzeRequest, AnalyzeResult } from './models';

/**
 * Prefijo de la API. NO es la dirección del backend, y esa es la gracia.
 *
 * En desarrollo `proxy.conf.json` reenvía `/api/*` a `http://127.0.0.1:8000`
 * quitando el prefijo; en despliegue lo hará nginx (decisión tomada para H4).
 * Para el navegador todo sale del MISMO origen, así que no hay CORS ni
 * preflight, y la SPA no tiene que saber dónde vive la API en cada entorno.
 */
const API = '/api';

@Injectable({ providedIn: 'root' })
export class AnalyzeService {
  private readonly http = inject(HttpClient);

  /**
   * Analiza un titular contrastando todas las señales disponibles.
   *
   * Devuelve un `Observable` **frío**: hasta que alguien se suscribe no se envía
   * nada, y cada suscripción es una petición nueva — o sea, un análisis nuevo,
   * otra ejecución de los modelos y otra entrada en el historial. Suscribirse
   * una sola vez por envío no es higiene, es corrección.
   *
   * Un 200 NO significa «no hubo problemas»: `/analyze` responde 200 aunque
   * alguna señal falle, porque cada una lleva su propio `status` y perder tres
   * análisis correctos porque el cuarto dio timeout sería el error de verdad.
   * Por el canal de error sólo llegan fallos de la PETICIÓN (422 con el titular
   * en blanco), del servidor o de la red.
   *
   * Devuelve el **sobre** `AnalyzeResult`, no el análisis pelado: dentro vienen
   * el análisis y el `id` con el que quedó registrado (#133), que es lo que
   * permitirá volver a él sin reejecutarlo.
   *
   * El `<AnalyzeResult>` de `post` **no comprueba nada**: es una afirmación
   * sobre lo que va a llegar, porque la respuesta viene por la red y TypeScript
   * no tiene contra qué contrastarla. Es la costura menos protegida de la
   * cadena, y en #133 se vio: el backend empezó a devolver el sobre y esto
   * siguió compilando con el tipo viejo.
   *
   * Lo que la sostiene es de dónde sale `AnalyzeResult` — de
   * `paths['/analyze']['post']` y no elegido a mano de `components`, así que
   * cambiar lo que devuelve la ruta cambia el tipo al regenerar el contrato. La
   * afirmación sigue sin verificarse aquí, pero ya no es una elección de quien
   * escribió esta línea. Ver `models.ts`.
   */
  analizar(peticion: AnalyzeRequest): Observable<AnalyzeResult> {
    return this.http.post<AnalyzeResult>(`${API}/analyze`, peticion);
  }
}
