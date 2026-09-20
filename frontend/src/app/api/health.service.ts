/**
 * Cliente de `GET /health`.
 *
 * Servicio propio y no un método más de `ToolsService` porque responden
 * preguntas distintas: el catálogo dice **qué servidores MCP hay y qué
 * ofrecen**, y esto dice **si las APIs de terceros contestan ahora mismo**. Uno
 * describe lo que el sistema es; el otro, lo que en este momento funciona.
 *
 * **Qué NO cubre, y conviene tenerlo delante:** el backend sondea `weather`,
 * `guardian` y `nyt`. Las señales NLP no están en la lista, así que un `ok` de
 * aquí no dice nada sobre si `detect_clickbait` responde — el 3 de septiembre
 * habría dicho `ok` con esa señal devolviendo 400 durante toda la mañana. Y
 * añadir el proveedor de HuggingFace tampoco lo arreglaría: `hf-inference`
 * responde, y aun así ese modelo no se sirve. La sonda que haría falta es **por
 * modelo**, y es trabajo de backend (#156).
 */
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API } from './base';
import type { HealthResult } from './models';

@Injectable({ providedIn: 'root' })
export class HealthService {
  private readonly http = inject(HttpClient);

  /**
   * Sondea las integraciones externas y devuelve el agregado más el detalle.
   *
   * **Cada suscripción son tres peticiones HTTP de verdad**, con un corte de
   * 5 s por sonda en el backend (`PROBE_TIMEOUT`). Es barato al abrir la
   * aplicación y a petición del usuario, y caro en un bucle de refresco: es
   * información que cambia despacio, y sondear en bucle multiplica el tráfico
   * contra APIs de terceros que además tienen cuota.
   *
   * **Que una integración esté caída NO llega por el canal de error**, igual
   * que en `/tools` y en `/analyze`: el backend responde 200 con `status` en
   * `degraded` o `down` y el motivo dentro de cada sonda. Por `error` sólo
   * llega que no se pueda hablar con la propia API, que significa otra cosa —
   * el backend no contesta— y hay que enseñarlo distinto.
   */
  estado(): Observable<HealthResult> {
    return this.http.get<HealthResult>(`${API}/health`);
  }
}
