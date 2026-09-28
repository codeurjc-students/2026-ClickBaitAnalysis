import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { SONDEO_MS } from '../api/chat.service';
import type { AgentInfo, ChatJob, Disponibilidad, PasoDeLaTraza } from '../api/models';
import { AsistentePage } from './asistente-page';

function agente(status: Disponibilidad['status'], detalle = 'Motivo publicable.'): AgentInfo {
  return {
    availability: { status, detail: detalle, model: 'qwen3.5:27b' },
    model_card: {
      model_id: 'qwen3.5:27b',
      name: 'Qwen 3.5, 27B',
      task: 'Narra lo que devuelven las herramientas.',
      type: 'opaque',
      limitations: ['Lento.'],
    },
    prompt: { name: '04-preciso', text: 'Eres el asistente…' },
    max_history_chars: 4000,
  };
}

/** Una vuelta del modelo que pide una señal, y la señal con su tarjeta. */
const PASOS: PasoDeLaTraza[] = [
  {
    kind: 'model',
    round: 1,
    content: '',
    tool_calls: ['detect_clickbait_lexical'],
    metrics: { prompt_tokens: 3700, output_tokens: 40, load_s: 0, total_s: 4 },
  },
  {
    kind: 'tool',
    round: 1,
    name: 'detect_clickbait_lexical',
    arguments: { headline: 'Top 5 Secrets' },
    status: 'ok',
    data: { score: 1, is_clickbait: true, matches: [], headline: 'Top 5 Secrets' },
    error: null,
    server: 'http://mcp:8765/mcp',
    duration_s: 0.2,
    signal: {
      name: 'detect_clickbait_lexical',
      label: 'Léxico por reglas',
      status: 'ok',
      dimension: 'form',
      type: 'interpretable',
      is_clickbait: true,
      data: { score: 1, is_clickbait: true, matches: [], headline: 'Top 5 Secrets' },
    },
  },
];

function lectura(
  status: ChatJob['status'],
  pasos: PasoDeLaTraza[] = [],
  final: ChatJob['result'] = null,
): ChatJob {
  return { id: 'abc', status, created_at: '2026-09-28T10:00:00Z', steps: pasos, result: final };
}

function respondida(answer: string, pasos: PasoDeLaTraza[] = PASOS): ChatJob {
  return lectura('done', pasos, {
    status: 'answered',
    answer,
    detail: null,
    rounds: 2,
    total_s: 12,
  });
}

describe('AsistentePage', () => {
  let fixture: ComponentFixture<AsistentePage>;
  let http: HttpTestingController;

  const html = () => fixture.nativeElement as HTMLElement;
  const texto = () => html().textContent ?? '';

  beforeEach(async () => {
    // Sólo el reloj del sondeo (`setInterval`, que es el que usa `timer`).
    // Angular sin zonas repinta con `setTimeout`, y ése se deja de verdad:
    // falseado, `whenStable` no terminaría nunca.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    await TestBed.configureTestingModule({
      imports: [AsistentePage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AsistentePage);
  });

  afterEach(() => {
    fixture.destroy();
    http.verify();
    vi.useRealTimers();
  });

  async function conAgente(status: Disponibilidad['status'], detalle?: string) {
    http.expectOne('/api/agent').flush(agente(status, detalle));
    await fixture.whenStable();
  }

  async function preguntar(pregunta: string) {
    fixture.componentInstance.mensaje.setValue(pregunta);
    html().querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  }

  /** Deja pasar el intervalo del sondeo y responde la lectura que sale. */
  async function sondeo(respuesta: ChatJob, espera = SONDEO_MS) {
    vi.advanceTimersByTime(espera);
    http.expectOne('/api/chat/abc').flush(respuesta);
    await fixture.whenStable();
  }

  // ----- Sin asistente (R6.14) -----

  it('sin asistente configurado lo explica, y no deja escribir', async () => {
    await conAgente('not_configured', 'El asistente no está configurado en este despliegue.');

    expect(html().querySelector('h2')?.textContent).toContain('no está en este despliegue');
    expect(texto()).toContain('El asistente no está configurado en este despliegue.');
    expect(html().querySelector('textarea')).toBeNull();
    expect(texto()).not.toContain('Volver a comprobar');
  });

  it('apagado, lo explica y deja volver a comprobar', async () => {
    await conAgente('unreachable', 'El asistente está apagado: se arranca bajo demanda.');

    expect(html().querySelector('h2')?.textContent).toContain('no se puede usar');
    expect(texto()).toContain('se arranca bajo demanda');
    expect(html().querySelector('textarea')).toBeNull();

    const boton = [...html().querySelectorAll('button')].find((candidato) =>
      candidato.textContent?.includes('Volver a comprobar'),
    )!;
    boton.click();
    await conAgente('available');

    expect(html().querySelector('textarea')).not.toBeNull();
  });

  it('enseña la ficha y el prompt en uso (R13.7, R13.5)', async () => {
    await conAgente('available');

    const sobre = html().querySelector('details.sobre')!;
    expect(sobre.textContent).toContain('qwen3.5:27b');
    expect(sobre.textContent).toContain('Lento.');
    expect(sobre.textContent).toContain('04-preciso');
    expect(sobre.textContent).toContain('Eres el asistente…');
  });

  // ----- La conversación -----

  it('la traza crece mientras trabaja, y la narración llega al final', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait «Top 5 Secrets»?');

    const envio = http.expectOne('/api/chat');
    expect(envio.request.body).toEqual({
      message: '¿Es clickbait «Top 5 Secrets»?',
      history: [],
    });
    envio.flush({ id: 'abc' });
    await sondeo(lectura('running', PASOS), 0);

    // A mitad: la tarjeta ya está, la narración todavía no, y no se puede
    // mandar otra pregunta.
    expect(html().querySelectorAll('app-senal-card').length).toBe(1);
    expect(texto()).toContain('Consulta detect_clickbait_lexical');
    expect(texto()).toContain('trabajando');
    expect(html().querySelector('.narracion')).toBeNull();
    expect(html().querySelector<HTMLButtonElement>('button[type=submit]')!.disabled).toBe(true);

    await sondeo(respondida('Es clickbait de forma.'));

    expect(html().querySelector('.narracion')?.textContent).toContain('Es clickbait de forma.');
    expect(html().querySelectorAll('app-senal-card').length).toBe(1);
    expect(texto()).not.toContain('trabajando');
    expect(html().querySelector<HTMLButtonElement>('button[type=submit]')!.disabled).toBe(false);
  });

  it('la traza se anuncia sin interrumpir (aria-live educado)', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(lectura('running', PASOS), 0);

    expect(html().querySelector('.traza')?.getAttribute('aria-live')).toBe('polite');
    expect(html().querySelector('.espera')?.getAttribute('role')).toBe('status');
  });

  it('en cola, lo dice', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(lectura('queued'), 0);

    expect(texto()).toContain('En cola');
  });

  // R6.13: sin narración, las tarjetas se ven igual, con un aviso discreto.
  it('con la narración vacía, las tarjetas se ven con un aviso discreto', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(
      lectura('done', PASOS, {
        status: 'empty_answer',
        answer: '',
        detail: null,
        rounds: 2,
        total_s: 9,
      }),
      0,
    );

    expect(html().querySelectorAll('app-senal-card').length).toBe(1);
    expect(html().querySelector('.aviso')?.textContent).toContain('no escribió un resumen');
    expect(html().querySelector('[role=alert]')).toBeNull();
  });

  it('una respuesta sin herramientas se marca', async () => {
    await conAgente('available');
    await preguntar('¿Qué es el clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(respondida('Es un titular que…', []), 0);

    expect(html().querySelector('.aviso')?.textContent).toContain(
      'no se apoya en ninguna herramienta',
    );
  });

  it('un fallo del agente se cuenta con su frase', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(
      lectura('done', [], {
        status: 'failed',
        answer: '',
        detail: 'El servidor del modelo tardó demasiado en responder.',
        rounds: 1,
        total_s: 300,
      }),
      0,
    );

    expect(html().querySelector('[role=alert]')?.textContent).toContain('tardó demasiado');
  });

  it('un 503 al preguntar se cuenta, y se vuelve a comprobar el asistente', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush(
      { detail: 'El asistente está atendiendo otras conversaciones y no caben más en espera.' },
      { status: 503, statusText: 'Service Unavailable' },
    );
    await fixture.whenStable();

    expect(html().querySelector('[role=alert]')?.textContent).toContain(
      'atendiendo otras conversaciones',
    );
    await conAgente('available');
  });

  it('la segunda pregunta lleva el texto de la primera como historial', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait «Top 5 Secrets»?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(respondida('Sí, de forma.'), 0);

    await preguntar('¿Y por qué?');
    const segunda = http.expectOne('/api/chat');
    expect(segunda.request.body).toEqual({
      message: '¿Y por qué?',
      history: [
        { role: 'user', content: '¿Es clickbait «Top 5 Secrets»?' },
        { role: 'assistant', content: 'Sí, de forma.' },
      ],
    });
    segunda.flush({ id: 'abc' });
    await sondeo(respondida('Porque usa «Top 5».'), 0);
  });
});
