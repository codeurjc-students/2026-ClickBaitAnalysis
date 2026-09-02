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

import type { AnalyzeRequest, AnalyzeResponse } from './models';

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
   */
  analizar(peticion: AnalyzeRequest): Observable<AnalyzeResponse> {
    return this.http.post<AnalyzeResponse>(`${API}/analyze`, peticion);
  }
}
