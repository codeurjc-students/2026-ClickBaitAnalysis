import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { HealthService } from './health.service';
import type { HealthResult } from './models';

/** Las tres integraciones que sondea el backend hoy, todas respondiendo. */
const TODO_BIEN: HealthResult = {
  status: 'ok',
  timestamp: '2026-09-07T13:00:00+00:00',
  integrations: {
    weather: { reachable: true, error: null },
    guardian: { reachable: true, error: null },
    nyt: { reachable: true, error: null },
  },
};

describe('HealthService', () => {
  let servicio: HealthService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(HealthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('sondea la salud contra el prefijo de la API', () => {
    servicio.estado().subscribe();

    const peticion = http.expectOne('/api/health');
    expect(peticion.request.method).toBe('GET');

    peticion.flush(TODO_BIEN);
  });

  // La razón de que el servicio exista: nadie más consulta esta ruta, así que
  // el prefijo tiene un único sitio donde equivocarse.
  it('no manda parámetros: el sondeo no se configura desde el cliente', () => {
    servicio.estado().subscribe();

    const peticion = http.expectOne('/api/health');
    expect(peticion.request.urlWithParams).toBe('/api/health');

    peticion.flush(TODO_BIEN);
  });

  // Una integración caída viaja en una respuesta CORRECTA, no por `error`. Es
  // el mismo patrón que `/tools` con un servidor inalcanzable y que `/analyze`
  // con una señal que falla: dar por bueno todo lo que llega por `next` dejaría
  // el semáforo en verde con dos APIs muertas.
  it('un degradado llega por next, con el motivo de cada sonda', () => {
    let recibida: HealthResult | undefined;
    servicio.estado().subscribe((salud) => (recibida = salud));

    http.expectOne('/api/health').flush({
      status: 'degraded',
      timestamp: '2026-09-07T13:00:00+00:00',
      integrations: {
        weather: { reachable: true, error: null },
        guardian: { reachable: true, error: null },
        nyt: { reachable: false, error: 'ReadTimeout: timed out' },
      },
    } satisfies HealthResult);

    expect(recibida?.status).toBe('degraded');
    expect(recibida?.integrations['nyt'].reachable).toBe(false);
    expect(recibida?.integrations['nyt'].error).toContain('timed out');
    expect(recibida?.integrations['guardian'].reachable).toBe(true);
  });

  // `integrations` es un diccionario abierto en el contrato: el backend puede
  // sondear una integración más sin que el frontend se entere. El tipo tiene
  // que dejarla pasar, porque enumerarlas aquí la escondería en silencio.
  it('acepta una integración que hoy no existe', () => {
    let recibida: HealthResult | undefined;
    servicio.estado().subscribe((salud) => (recibida = salud));

    http.expectOne('/api/health').flush({
      status: 'ok',
      timestamp: '2026-09-07T13:00:00+00:00',
      integrations: {
        weather: { reachable: true, error: null },
        guardian: { reachable: true, error: null },
        nyt: { reachable: true, error: null },
        inventada: { reachable: true, error: null },
      },
    } satisfies HealthResult);

    expect(Object.keys(recibida?.integrations ?? {})).toContain('inventada');
  });
});
