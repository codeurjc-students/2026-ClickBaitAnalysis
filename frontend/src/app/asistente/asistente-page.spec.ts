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
import { CLAVE_GUARDADO } from './conversacion';

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

/** Una vuelta que pide noticias, y la lista: una con enlace y otra sin él. */
const NOTICIAS: PasoDeLaTraza[] = [
  {
    kind: 'model',
    round: 1,
    content: '',
    tool_calls: ['get_nyt_news'],
    metrics: { prompt_tokens: 3700, output_tokens: 40, load_s: 0, total_s: 4 },
  },
  {
    kind: 'tool',
    round: 1,
    name: 'get_nyt_news',
    arguments: { topic: 'artificial intelligence' },
    status: 'ok',
    data: {
      result: [
        {
          title: 'College Leaders Are Using A.I.',
          url: 'https://www.nytimes.com/2026/09/29/us/college-ai.html',
          date: '2026-09-29T10:00:00Z',
        },
        { title: 'A Headline Without Link', url: null, date: null },
      ],
    },
    error: null,
    server: 'http://mcp:8765/mcp',
    duration_s: 0.4,
    signal: null,
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
    // Sólo el reloj del sondeo (`setInterval`, que es el que usa `timer`) y
    // `Date`, que es con lo que se mide cuánto lleva una pregunta. Angular sin
    // zonas repinta con `setTimeout`, y ése se deja de verdad: falseado,
    // `whenStable` no terminaría nunca.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
    // La pantalla guarda la conversación en `sessionStorage` (#209), y jsdom lo
    // comparte entre los tests de un fichero.
    sessionStorage.clear();
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
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  /**
   * Como recargar la página o volver a la sección: una pantalla nueva, con lo
   * que dejó guardado la anterior.
   */
  async function recargar() {
    fixture.destroy();
    fixture = TestBed.createComponent(AsistentePage);
    await conAgente('available');
  }

  function boton(texto: string): HTMLButtonElement {
    return [...html().querySelectorAll('button')].find((candidato) =>
      candidato.textContent?.includes(texto),
    )!;
  }

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
    expect(texto()).toContain('Leyendo los resultados');
    expect(html().querySelector('.narracion')).toBeNull();
    expect(html().querySelector<HTMLButtonElement>('button[type=submit]')!.disabled).toBe(true);

    await sondeo(respondida('Es clickbait de forma.'));

    expect(html().querySelector('.narracion')?.textContent).toContain('Es clickbait de forma.');
    expect(html().querySelectorAll('app-senal-card').length).toBe(1);
    expect(texto()).not.toContain('Leyendo los resultados');
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

  // #210: el enlace ya estaba desde #191; faltaba decir que abre otra pestaña.
  // Con la vista se nota el salto; con un lector de pantalla sólo se oye una
  // página nueva, y «Atrás» no vuelve a la conversación.
  it('cada noticia enlaza a la suya, y avisa al lector de pantalla de la pestaña nueva', async () => {
    await conAgente('available');
    await preguntar('Tráeme noticias de NYT sobre inteligencia artificial');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(respondida('Diez noticias.', NOTICIAS), 0);

    const [conEnlace, sinEnlace] = [...html().querySelectorAll('.noticias li')];
    const enlace = conEnlace.querySelector('a')!;
    expect(enlace.getAttribute('href')).toBe('https://www.nytimes.com/2026/09/29/us/college-ai.html');
    expect(enlace.getAttribute('target')).toBe('_blank');
    expect(enlace.getAttribute('rel')).toBe('noopener');

    // El titular, en inglés; el aviso, en castellano y fuera del `lang="en"`,
    // para que el lector no lo pronuncie como inglés.
    expect(enlace.getAttribute('lang')).toBeNull();
    expect(enlace.querySelector('[lang="en"]')?.textContent).toBe('College Leaders Are Using A.I.');
    const aviso = enlace.querySelector('.solo-lector');
    expect(aviso?.textContent).toContain('se abre en una pestaña nueva');
    expect(aviso?.closest('[lang="en"]')).toBeNull();

    // La fecha, separada del titular: Angular quitaba el espacio entre los dos.
    expect(conEnlace.querySelector('.noticia__fecha')?.textContent).toBe(' · 2026-09-29');

    expect(sinEnlace.querySelector('a')).toBeNull();
    expect(sinEnlace.querySelector('[lang="en"]')?.textContent).toBe('A Headline Without Link');
  });

  // ----- Lo que sobrevive a recargar (#209) -----

  it('al recargar o volver a la sección, la conversación sigue ahí', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait «Top 5 Secrets»?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(respondida('Es clickbait de forma.'), 0);

    await recargar();

    expect(html().querySelector('.pregunta')?.textContent).toContain('Top 5 Secrets');
    expect(html().querySelectorAll('app-senal-card').length).toBe(1);
    expect(html().querySelector('.narracion')?.textContent).toContain('Es clickbait de forma.');
    // Sale del navegador: lo terminado no se le vuelve a pedir al servidor.
    vi.advanceTimersByTime(SONDEO_MS);
    http.expectNone('/api/chat/abc');

    // Y la pregunta siguiente lleva lo recuperado como historial.
    await preguntar('¿Y por qué?');
    expect(http.expectOne('/api/chat').request.body).toEqual({
      message: '¿Y por qué?',
      history: [
        { role: 'user', content: '¿Es clickbait «Top 5 Secrets»?' },
        { role: 'assistant', content: 'Es clickbait de forma.', tools: ['detect_clickbait_lexical'] },
      ],
    });
  });

  it('una pregunta en marcha se sigue tras recargar', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(lectura('running', PASOS), 0);

    await recargar();

    expect(texto()).toContain('Leyendo los resultados');
    await sondeo(respondida('Es clickbait de forma.'), 0);
    expect(html().querySelector('.narracion')?.textContent).toContain('Es clickbait de forma.');
  });

  it('si la conversación ya caducó en el servidor, lo dice', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(lectura('running', PASOS), 0);

    await recargar();
    vi.advanceTimersByTime(0);
    http
      .expectOne('/api/chat/abc')
      .flush({ detail: 'Not Found' }, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();

    expect(texto()).toContain('ya no está en el servidor');
    expect(html().querySelector<HTMLButtonElement>('button[type=submit]')!.disabled).toBe(false);
  });

  it('una pregunta que el servidor no llegó a aceptar se marca, y se puede volver a preguntar', async () => {
    await conAgente('available');
    sessionStorage.setItem(
      CLAVE_GUARDADO,
      JSON.stringify([
        { pregunta: '¿Hola?', id: null, trabajo: null, error: null, enviadaEl: 0, leidaEl: null },
      ]),
    );

    await recargar();

    expect(texto()).toContain('antes de que el asistente aceptara la pregunta');
    expect(html().querySelector<HTMLButtonElement>('button[type=submit]')!.disabled).toBe(false);
  });

  it('sin almacenamiento, funciona como hoy y avisa de que no se guardará', async () => {
    await conAgente('available');
    const lleno = () => {
      throw new DOMException('No se puede guardar.', 'QuotaExceededError');
    };
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(lleno);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(lleno);

    await recargar();
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(respondida('Es clickbait de forma.'), 0);

    expect(html().querySelector('.narracion')?.textContent).toContain('Es clickbait de forma.');
    const aviso = html().querySelector('.aviso--guardado');
    expect(aviso?.textContent).toContain('no deja guardar la conversación');
    expect(aviso?.getAttribute('role')).toBeNull(); // informa, no interrumpe
  });

  it('empezar de nuevo vacía la conversación y lo guardado', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(respondida('Es clickbait de forma.'), 0);

    boton('Empezar una conversación nueva').click();
    await fixture.whenStable();

    expect(html().querySelector('.conversacion')).toBeNull();
    expect(sessionStorage.getItem(CLAVE_GUARDADO)).toBeNull();
    expect(document.activeElement).toBe(html().querySelector('textarea'));
    expect(boton('Empezar una conversación nueva')).toBeUndefined();
  });

  // El servidor seguiría trabajando en una pregunta que ya nadie miraría.
  it('con una pregunta en marcha, no se puede empezar de nuevo', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(lectura('running', PASOS), 0);

    expect(boton('Empezar una conversación nueva').disabled).toBe(true);
  });

  // Lo que destapó la aceptación de #191: tras un resultado, una vuelta de
  // 98,8 s sin nada nuevo en pantalla se leyó como un cuelgue.
  it('una espera larga dice en qué está y cuánto lleva', async () => {
    await conAgente('available');
    await preguntar('¿Es clickbait?');
    http.expectOne('/api/chat').flush({ id: 'abc' });
    await sondeo(lectura('running', PASOS), 0);

    expect(html().querySelector('.espera')?.textContent).toContain('lleva 0 s');
    expect(texto()).not.toContain('un par de minutos');

    // 80 s de razonamiento: los ticks del sondeo se saltan mientras la
    // lectura sigue en camino, así que sale una sola petición.
    vi.advanceTimersByTime(80_000);
    http.expectOne('/api/chat/abc').flush(lectura('running', PASOS));
    await fixture.whenStable();

    const espera = html().querySelector('.espera')?.textContent ?? '';
    expect(espera).toContain('Leyendo los resultados y decidiendo el siguiente paso');
    expect(espera).toContain('lleva 1 min 20 s');
    expect(espera).toContain('un par de minutos');
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

  it('la segunda pregunta lleva la primera como historial, con sus herramientas', async () => {
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
        // Los nombres de lo que consultó, sin resultados (#192).
        { role: 'assistant', content: 'Sí, de forma.', tools: ['detect_clickbait_lexical'] },
      ],
    });
    segunda.flush({ id: 'abc' });
    await sondeo(respondida('Porque usa «Top 5».'), 0);
  });
});
