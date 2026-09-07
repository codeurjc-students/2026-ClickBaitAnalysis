import { provideHttpClient, HttpErrorResponse } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import type { CatalogResult, ExecuteResult } from './models';
import { ToolsService } from './tools.service';

/**
 * Catálogo con un servidor sano y otro caído, que es el caso que hay que tener
 * delante: llega por el canal de éxito, con el motivo dentro, y las
 * herramientas del que sí respondió se sirven igual.
 */
const CATALOGO: CatalogResult = {
  servers: [
    { url: 'http://127.0.0.1:8010/mcp', name: 'tfg', status: 'ok', tool_count: 1 },
    {
      url: 'http://127.0.0.1:8011/mcp',
      status: 'unreachable',
      // Lo publica el contrato aunque no responda: cero herramientas, no
      // ausencia de dato.
      tool_count: 0,
      detail: 'ConnectError: All connection attempts failed',
    },
  ],
  tools: [
    {
      name: 'detect_clickbait_lexical',
      description: 'Detecta clickbait por vocabulario.',
      input_schema: {
        type: 'object',
        properties: { headline: { type: 'string' } },
        required: ['headline'],
      },
      server: 'tfg',
    },
  ],
  degraded: true,
};

describe('ToolsService', () => {
  let servicio: ToolsService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(ToolsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('pide el catálogo a /api/tools por GET', () => {
    servicio.catalogo().subscribe();

    const peticion = http.expectOne('/api/tools');
    expect(peticion.request.method).toBe('GET');

    peticion.flush(CATALOGO);
  });

  // El servidor caído no es un fallo de la llamada: si algún día llegara por el
  // canal de error, la pantalla dejaría de enseñar el catálogo entero por uno
  // que no respondió.
  it('entrega el catálogo aunque venga degradado', () => {
    let recibido: CatalogResult | undefined;
    servicio.catalogo().subscribe((catalogo) => {
      recibido = catalogo;
    });

    http.expectOne('/api/tools').flush(CATALOGO);

    expect(recibido?.degraded).toBe(true);
    expect(recibido?.tools.length).toBe(1);
    expect(recibido?.servers[1].detail).toContain('ConnectError');
  });

  it('ejecuta una herramienta con sus argumentos en el cuerpo', () => {
    servicio
      .ejecutar('detect_clickbait_lexical', { headline: 'Un titular' })
      .subscribe();

    const peticion = http.expectOne(
      '/api/tools/detect_clickbait_lexical/execute',
    );
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      arguments: { headline: 'Un titular' },
    });

    peticion.flush({ tool: 'detect_clickbait_lexical', server: 'tfg', status: 'ok' });
  });

  // El nombre lo declara el servidor MCP, no una lista de aquí. Sin escapar, un
  // espacio partiría la URL y la petición iría a otra ruta.
  it('escapa el nombre de la herramienta en la URL', () => {
    servicio.ejecutar('nombre raro/con barra', {}).subscribe();

    const peticion = http.expectOne(
      '/api/tools/nombre%20raro%2Fcon%20barra/execute',
    );

    peticion.flush({ tool: 'nombre raro/con barra', server: 'tfg', status: 'ok' });
  });

  // Lo que sostiene el contrato: la herramienta falló, la petición no. Si esto
  // llegara por `error`, quien se suscribe perdería el `detail` que explica qué
  // pasó.
  it('un fallo de la herramienta llega por next, no por error', () => {
    const FALLO: ExecuteResult = {
      tool: 'get_nyt_news',
      server: 'tfg',
      status: 'error',
      detail: 'La API de NYT respondió 503.',
    };

    let recibido: ExecuteResult | undefined;
    let error: unknown;
    servicio.ejecutar('get_nyt_news', { topic: 'clima' }).subscribe({
      next: (respuesta) => {
        recibido = respuesta;
      },
      error: (fallo: unknown) => {
        error = fallo;
      },
    });

    http.expectOne('/api/tools/get_nyt_news/execute').flush(FALLO);

    expect(error).toBeUndefined();
    expect(recibido?.status).toBe('error');
    expect(recibido?.detail).toContain('503');
  });

  // Y al revés: agotar la espera SÍ es un error de la llamada, y con un código
  // propio. Fundirlo con el `status: error` diría que el análisis falló, que es
  // justo lo que no se sabe (#113).
  it('el 504 de espera agotada llega por el canal de error', () => {
    let recibido: HttpErrorResponse | undefined;
    servicio.ejecutar('detect_clickbait', { headline: 'Un titular' }).subscribe({
      error: (fallo: HttpErrorResponse) => {
        recibido = fallo;
      },
    });

    http
      .expectOne('/api/tools/detect_clickbait/execute')
      .flush(
        { detail: 'La herramienta tardó más de 60 s.' },
        { status: 504, statusText: 'Gateway Timeout' },
      );

    expect(recibido?.status).toBe(504);
  });

  it('no llama a la API hasta que alguien se suscribe', () => {
    servicio.catalogo();
    servicio.ejecutar('detect_clickbait', { headline: 'Un titular' });

    http.expectNone('/api/tools');
    http.expectNone('/api/tools/detect_clickbait/execute');
  });
});
