/**
 * Cliente de `POST /chat`, `GET /chat/{job_id}` y `GET /agent` (#189, #191).
 *
 * Una conversación no se pide y se espera: `POST /chat` responde al instante
 * con un id, y la respuesta se va leyendo con `GET /chat/{job_id}` mientras el
 * agente trabaja, porque un bucle con el 27B tarda de 13 a 36 s y la traza
 * crece entre lectura y lectura. `seguir` es ese sondeo.
 *
 * Como los demás servicios: los componentes inyectan esto y nunca
 * `HttpClient` a pelo, así que las rutas viven en un único sitio.
 */
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, exhaustMap, retry, takeWhile, throwError, timer } from 'rxjs';

import { API } from './base';
import type {
  AgentInfo,
  ChatAceptada,
  ChatBody,
  ChatJob,
  Turno,
} from './models';

/**
 * Cada cuánto se lee una conversación en marcha (decidido en #189).
 *
 * Va en el presupuesto general del limitador, 60 por minuto y cliente: a 2 s
 * son 30, así que quedan otras 30 para lo demás. Un bucle de 36 s son 18
 * lecturas; medido en la máquina 1, entre 15 y 33 por conversación.
 */
export const SONDEO_MS = 2000;

/** Si un 429 llega sin `Retry-After`, cuánto esperar antes de volver a leer. */
const ESPERA_POR_DEFECTO_MS = 5000;

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly http = inject(HttpClient);

  /**
   * Si el asistente se puede usar ahora, su ficha, su prompt y el tope del
   * historial. Barato de pedir: que no haya nadie escuchando se sabe en
   * 0,2 ms (#181), y por eso no se cachea.
   */
  agente(): Observable<AgentInfo> {
    return this.http.get<AgentInfo>(`${API}/agent`);
  }

  /**
   * Manda un mensaje con el texto de los turnos anteriores, y devuelve el id
   * de la conversación aceptada. El servidor no guarda nada entre turnos: el
   * historial es de quien llama, y tiene que caber en `max_history_chars`.
   *
   * **Un 503 no es un fallo de la petición**: el asistente no está disponible
   * o está atendiendo otras conversaciones, y el `detail` dice cuál con una
   * frase que se puede enseñar tal cual.
   */
  preguntar(mensaje: string, historial: Turno[]): Observable<ChatAceptada> {
    const cuerpo: ChatBody = { message: mensaje, history: historial };
    return this.http.post<ChatAceptada>(`${API}/chat`, cuerpo);
  }

  /** La conversación tal como está ahora. 404 si no existe o ya caducó. */
  leer(id: string): Observable<ChatJob> {
    return this.http.get<ChatJob>(`${API}/chat/${encodeURIComponent(id)}`);
  }

  /**
   * Lee la conversación cada `SONDEO_MS` hasta que termina, y emite cada
   * lectura: la última es la que trae `done`.
   *
   * - `exhaustMap` y no `switchMap`: si una lectura tarda más que el
   *   intervalo, la siguiente se salta en vez de cancelar la que está en
   *   camino. Así no se amontonan peticiones sobre una conexión lenta.
   * - **Un 429 no corta la conversación**: se espera lo que diga
   *   `Retry-After` y se vuelve a leer. Ese límite es del RITMO, no de la
   *   conversación, que sigue avanzando en el servidor mientras tanto.
   * - Cualquier otro fallo —el 404 de una conversación caducada, la API
   *   caída— sí corta, y lo cuenta quien se suscribe.
   */
  seguir(id: string): Observable<ChatJob> {
    return timer(0, SONDEO_MS).pipe(
      exhaustMap(() =>
        this.leer(id).pipe(
          retry({
            delay: (fallo: unknown) =>
              fallo instanceof HttpErrorResponse && fallo.status === 429
                ? timer(esperaDe(fallo))
                : throwError(() => fallo),
          }),
        ),
      ),
      takeWhile((trabajo) => trabajo.status !== 'done', true),
    );
  }
}

/** Lo que pide esperar un 429, en milisegundos. */
function esperaDe(fallo: HttpErrorResponse): number {
  const segundos = Number(fallo.headers.get('Retry-After'));
  return Number.isFinite(segundos) && segundos > 0
    ? segundos * 1000
    : ESPERA_POR_DEFECTO_MS;
}
