import { provideHttpClient, HttpErrorResponse } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ChatService, SONDEO_MS } from './chat.service';
import type { ChatJob } from './models';

/** Una lectura de la conversación, en el estado que se diga. */
function trabajo(status: ChatJob['status']): ChatJob {
  return {
    id: 'abc',
    status,
    created_at: '2026-09-28T10:00:00Z',
    steps: [],
    result:
      status === 'done'
        ? { status: 'answered', answer: 'Hecho.', detail: null, rounds: 1, total_s: 4 }
        : null,
  };
}

describe('ChatService', () => {
  let servicio: ChatService;
  let http: HttpTestingController;

  beforeEach(() => {
    // El sondeo va con `timer`: con el reloj de mentira se adelanta el tiempo
    // en vez de esperarlo, y se ve exactamente cuándo sale cada lectura.
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(ChatService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  it('pregunta la disponibilidad a /api/agent', () => {
    servicio.agente().subscribe();
    expect(http.expectOne('/api/agent').request.method).toBe('GET');
  });

  it('manda el mensaje y el historial a /api/chat por POST', () => {
    const historial = [
      { role: 'user' as const, content: 'Hola' },
      { role: 'assistant' as const, content: '¿Qué titular?' },
    ];
    servicio.preguntar('¿Es clickbait?', historial).subscribe();

    const peticion = http.expectOne('/api/chat');
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      message: '¿Es clickbait?',
      history: historial,
    });
  });

  it('sondea cada 2 s hasta que la conversación termina, y entonces para', () => {
    const vistos: string[] = [];
    let terminado = false;
    servicio.seguir('abc').subscribe({
      next: (lectura) => vistos.push(lectura.status),
      complete: () => (terminado = true),
    });

    vi.advanceTimersByTime(0);
    http.expectOne('/api/chat/abc').flush(trabajo('queued'));
    vi.advanceTimersByTime(SONDEO_MS);
    http.expectOne('/api/chat/abc').flush(trabajo('running'));
    vi.advanceTimersByTime(SONDEO_MS);
    http.expectOne('/api/chat/abc').flush(trabajo('done'));

    // Terminada, no se vuelve a preguntar por ella.
    vi.advanceTimersByTime(SONDEO_MS * 5);
    http.expectNone('/api/chat/abc');
    expect(vistos).toEqual(['queued', 'running', 'done']);
    expect(terminado).toBe(true);
  });

  it('ante un 429 espera lo que diga Retry-After y sigue leyendo', () => {
    const vistos: string[] = [];
    servicio.seguir('abc').subscribe((lectura) => vistos.push(lectura.status));

    vi.advanceTimersByTime(0);
    http.expectOne('/api/chat/abc').flush(
      { detail: 'Demasiadas peticiones.' },
      { status: 429, statusText: 'Too Many Requests', headers: { 'Retry-After': '3' } },
    );

    // Ni un segundo antes de lo pedido, aunque el intervalo del sondeo pase.
    vi.advanceTimersByTime(2999);
    http.expectNone('/api/chat/abc');
    vi.advanceTimersByTime(1);
    http.expectOne('/api/chat/abc').flush(trabajo('done'));

    expect(vistos).toEqual(['done']);
  });

  it('una conversación caducada corta el sondeo con su 404', () => {
    let fallo: HttpErrorResponse | null = null;
    servicio.seguir('abc').subscribe({
      error: (error: HttpErrorResponse) => (fallo = error),
    });

    vi.advanceTimersByTime(0);
    http.expectOne('/api/chat/abc').flush(
      { detail: 'No hay ninguna conversación con ese id; puede que haya caducado.' },
      { status: 404, statusText: 'Not Found' },
    );

    vi.advanceTimersByTime(SONDEO_MS * 3);
    http.expectNone('/api/chat/abc');
    expect(fallo).not.toBeNull();
    expect((fallo as HttpErrorResponse | null)?.status).toBe(404);
  });
});
