/**
 * Cliente de `GET /tools` y `POST /tools/{name}/execute`.
 *
 * Un solo servicio para las dos rutas porque son la misma conversación: el
 * catálogo dice qué herramientas hay y qué parámetros pide cada una, y ejecutar
 * es usar justo eso. Partirlo en dos obligaría a la pantalla de Sistema a
 * inyectar dos cosas para una sola pregunta.
 *
 * Como `analyze.service.ts`: los componentes inyectan esto y nunca `HttpClient`
 * a pelo, así que las rutas viven en un único sitio.
 */
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API } from './base';
import type { Argumentos, CatalogResult, ExecuteBody, ExecuteResult } from './models';

@Injectable({ providedIn: 'root' })
export class ToolsService {
  private readonly http = inject(HttpClient);

  /**
   * Pide el catálogo: qué servidores se consultaron y qué ofrecen.
   *
   * **Un servidor caído no llega por el canal de error.** El backend responde
   * 200 con ese servidor en `unreachable` y su motivo, y sirve las herramientas
   * de los demás — la misma degradación que las señales de `/analyze`. Quien se
   * suscriba tiene que mirar `servers`, o enseñará un catálogo incompleto como
   * si estuviera entero; `degraded` viene ya calculado para no tener que
   * recorrer la lista.
   *
   * Cada suscripción es un handshake nuevo contra cada servidor (~0,2 s
   * medidos, ver `api/catalog.py`). Es barato para abrir la pantalla y recargar
   * a mano, y caro en bucle.
   */
  catalogo(): Observable<CatalogResult> {
    return this.http.get<CatalogResult>(`${API}/tools`);
  }

  /**
   * Ejecuta una herramienta suelta con los argumentos que pida su esquema.
   *
   * `encodeURIComponent` porque el nombre lo declara el servidor MCP y no una
   * lista escrita aquí: hoy todos son identificadores de Python, pero el
   * protocolo no lo garantiza y basta un espacio para partir la URL.
   *
   * **Que la herramienta falle llega por `next`, no por `error`**: 200 con
   * `status` en `error` y su `detail`, porque la petición era válida y el
   * servidor la atendió. Dar por bueno todo lo que llega por `next` enseñaría
   * un resultado vacío como si fuera correcto.
   *
   * Por el canal de error quedan tres cosas distintas, y conviene no fundirlas
   * al enseñarlas: **404** la herramienta no existe, **422** los argumentos no
   * encajan en su esquema —el backend valida antes de invocar, así que dice
   * cuál— y **504** se agotó la espera. El 504 no significa que fallara: en
   * #113 la herramienta terminó bien a los 151 s con la API ya desistida. Lo
   * que falló es la espera.
   */
  ejecutar(nombre: string, argumentos: Argumentos): Observable<ExecuteResult> {
    const cuerpo: ExecuteBody = { arguments: argumentos };
    return this.http.post<ExecuteResult>(
      `${API}/tools/${encodeURIComponent(nombre)}/execute`,
      cuerpo,
    );
  }
}
