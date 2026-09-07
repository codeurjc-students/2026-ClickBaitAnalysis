import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { HistoryService } from './history.service';
import type { HistoryResult } from './models';

/** Una página vacía, con la retención que publica el backend. */
const PAGINA: HistoryResult = {
  items: [],
  total: 0,
  limit: 20,
  offset: 0,
  retention: { max_entries: 500, max_days: 30 },
};

describe('HistoryService', () => {
  let servicio: HistoryService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(HistoryService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('pide la primera página sin parámetros cuando no hay filtros', () => {
    servicio.pagina().subscribe();

    const peticion = http.expectOne('/api/history');
    expect(peticion.request.method).toBe('GET');
    expect(peticion.request.urlWithParams).toBe('/api/history');

    peticion.flush(PAGINA);
  });

  it('manda los filtros que tienen valor', () => {
    servicio.pagina({ kind: 'analysis', verdict: 'deceptive', limit: 50, offset: 20 }).subscribe();

    const peticion = http.expectOne(
      (candidata) => candidata.url === '/api/history',
    );
    expect(peticion.request.params.get('kind')).toBe('analysis');
    expect(peticion.request.params.get('verdict')).toBe('deceptive');
    expect(peticion.request.params.get('limit')).toBe('50');
    expect(peticion.request.params.get('offset')).toBe('20');

    peticion.flush(PAGINA);
  });

  // Mandar `verdict=` vacío no es no filtrar: el backend lo tomaría como un
  // filtro por la cadena vacía y devolvería cero entradas.
  it('un filtro sin valor no viaja', () => {
    servicio.pagina({ kind: 'tool', verdict: '', tool: null, since: undefined }).subscribe();

    const peticion = http.expectOne(
      (candidata) => candidata.url === '/api/history',
    );
    expect(peticion.request.urlWithParams).toBe('/api/history?kind=tool');

    peticion.flush(PAGINA);
  });

  it('una entrada se pide por su id', () => {
    servicio.entrada(42).subscribe();

    const peticion = http.expectOne('/api/history/42');
    expect(peticion.request.method).toBe('GET');

    peticion.flush({
      id: 42,
      created_at: '2026-09-06T09:00:00Z',
      kind: 'analysis',
      origin: 'api',
      status: 'ok',
      payload: {},
    });
  });

  // MEDIDO, y salió al revés de lo que supuse: `HttpParams` SÍ codifica el `+`
  // como `%2B`, así que una fecha con desfase llega entera. El aviso del
  // contrato —en una cadena de consulta un `+` es un ESPACIO— vale para URLs
  // escritas a mano, no para esta vía.
  //
  // El test lo fija porque el día que alguien cambie el codificador el síntoma
  // sería un 422 intermitente, sufrido sólo por quien esté en un huso con
  // desfase distinto de cero.
  it('codifica el + de una fecha con desfase, que es lo que la salva', () => {
    servicio.pagina({ since: '2026-09-06T00:00:00+02:00' }).subscribe();

    const peticion = http.expectOne(
      (candidata) => candidata.url === '/api/history',
    );
    expect(peticion.request.urlWithParams).toContain('%2B02:00');
    // El valor de dentro no se toca: lo codificado es la URL, no el parámetro.
    expect(peticion.request.params.get('since')).toBe('2026-09-06T00:00:00+02:00');

    peticion.flush(PAGINA);
  });

  it('la forma segura de mandar una fecha es toISOString', () => {
    const desde = new Date(Date.UTC(2026, 8, 6, 0, 0, 0));
    servicio.pagina({ since: desde.toISOString() }).subscribe();

    const peticion = http.expectOne(
      (candidata) => candidata.url === '/api/history',
    );
    expect(peticion.request.params.get('since')).toBe('2026-09-06T00:00:00.000Z');
    expect(peticion.request.urlWithParams).not.toContain('+');

    peticion.flush(PAGINA);
  });
});
