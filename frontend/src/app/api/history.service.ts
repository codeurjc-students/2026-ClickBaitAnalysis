/**
 * Cliente de `GET /history` y `GET /history/{entry_id}`.
 *
 * El historial es de sólo lectura desde la interfaz: quien escribe en él es la
 * propia API al atender un `/analyze` o un `/execute`. Por eso aquí no hay
 * ningún método que cree ni borre — y la retención, que sí borra, es del
 * backend y viaja publicada en cada página para que la pantalla la explique.
 */
import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API } from './base';
import type {
  HistoryEntryResult,
  HistoryQuery,
  HistoryResult,
} from './models';

@Injectable({ providedIn: 'root' })
export class HistoryService {
  private readonly http = inject(HttpClient);

  /**
   * Una página del historial, de la más reciente a la más antigua.
   *
   * Los filtros llegan con el tipo que publica el contrato, así que `limit` y
   * `offset` no pueden salirse de los topes sin que el compilador lo vea antes
   * que el 422.
   *
   * **Una fecha con desfase viaja entera**, y conviene saber por qué. El
   * contrato avisa de que en una cadena de consulta un `+` significa ESPACIO,
   * de modo que un `...T00:00:00+02:00` escrito a pelo en la URL llega partido
   * y devuelve 422. Medido: `HttpParams` lo codifica como `%2B`, así que por
   * esta vía no pasa. Hay un test que lo fija, porque si algún día cambia el
   * codificador el síntoma sería un 422 intermitente que sólo sufre quien esté
   * en un huso con desfase.
   *
   * Aún así lo natural es mandar `Date.toISOString()`, que ya produce UTC con
   * sufijo `Z` y no depende de nada de esto.
   */
  pagina(filtros: HistoryQuery = {}): Observable<HistoryResult> {
    return this.http.get<HistoryResult>(`${API}/history`, {
      params: this.comoParametros(filtros),
    });
  }

  /**
   * Una entrada concreta, con su `payload` entero.
   *
   * Es lo que permite volver a un análisis sin reejecutarlo — que además de
   * tardar podría dar otro resultado, porque las señales remotas no son
   * deterministas.
   *
   * **Un 404 aquí es normal, no excepcional**: la retención poda entradas, así
   * que un enlace guardado deja de existir con el tiempo. Quien lo consuma
   * tiene que distinguirlo de un fallo de red y decirlo con esas palabras.
   */
  entrada(id: number): Observable<HistoryEntryResult> {
    return this.http.get<HistoryEntryResult>(`${API}/history/${id}`);
  }

  /**
   * Convierte el filtro en parámetros, dejando fuera lo que no tiene valor.
   *
   * Mandar `verdict=` vacío no es lo mismo que no mandarlo: el backend lo
   * tomaría como un filtro por la cadena vacía y devolvería cero entradas. Es
   * la misma distinción que el formulario generado de #128.
   *
   * `HttpParams` es INMUTABLE: `set` devuelve otro objeto, así que el
   * resultado hay que reasignarlo o se pierde.
   */
  private comoParametros(filtros: HistoryQuery): HttpParams {
    let parametros = new HttpParams();

    for (const [nombre, valor] of Object.entries(filtros)) {
      if (valor === null || valor === undefined || valor === '') continue;
      parametros = parametros.set(nombre, String(valor));
    }

    return parametros;
  }
}
