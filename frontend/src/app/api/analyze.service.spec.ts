import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AnalyzeService } from './analyze.service';
import type { AnalyzeResponse } from './models';

/**
 * Respuesta mínima que sigue validando contra el contrato: sin señales y con
 * `no_data`, que es lo que devuelve el backend cuando ninguna llegó a
 * pronunciarse. Aquí no se prueba el análisis, sólo el transporte.
 */
const RESPUESTA: AnalyzeResponse = {
  headline: 'Un titular',
  content: null,
  signals: [],
  dimensions: [],
  verdict: 'no_data',
};

describe('AnalyzeService', () => {
  let servicio: AnalyzeService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(AnalyzeService);
    http = TestBed.inject(HttpTestingController);
  });

  // Falla si quedó alguna petición sin atender: es lo que destapa un envío
  // duplicado, que en esta API significa dos análisis y dos entradas de
  // historial.
  afterEach(() => http.verify());


  it('envía el titular a /api/analyze por POST', () => {
    servicio.analizar({ headline: 'Un titular' }).subscribe();

    const peticion = http.expectOne('/api/analyze');
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({ headline: 'Un titular' });

    peticion.flush(RESPUESTA);
  });

  it('incluye el contenido cuando se envía', () => {
    servicio
      .analizar({ headline: 'Un titular', content: 'El cuerpo' })
      .subscribe();

    const peticion = http.expectOne('/api/analyze');
    expect(peticion.request.body).toEqual({
      headline: 'Un titular',
      content: 'El cuerpo',
    });

    peticion.flush(RESPUESTA);
  });

  it('entrega la respuesta tal cual la devuelve la API', () => {
    let recibida: AnalyzeResponse | undefined;
    servicio.analizar({ headline: 'Un titular' }).subscribe((r) => {
      recibida = r;
    });

    http.expectOne('/api/analyze').flush(RESPUESTA);

    expect(recibida).toEqual(RESPUESTA);
  });

  // Documenta la propiedad que hace correcto suscribirse una sola vez: el
  // Observable es FRÍO, así que llamar al método no dispara nada. Si algún día
  // se cambia por algo caliente (un `Subject`, una promesa compartida), este
  // test lo dice en vez de dejarlo pasar.
  it('no llama a la API hasta que alguien se suscribe', () => {
    servicio.analizar({ headline: 'Un titular' });

    http.expectNone('/api/analyze');
  });
});
