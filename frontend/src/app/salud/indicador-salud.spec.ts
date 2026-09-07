import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { IndicadorSalud } from './indicador-salud';
import type { HealthResult } from '../api/models';

const TODO_BIEN: HealthResult = {
  status: 'ok',
  timestamp: '2026-09-07T13:00:00+00:00',
  integrations: {
    weather: { reachable: true, error: null },
    guardian: { reachable: true, error: null },
    nyt: { reachable: true, error: null },
  },
};

const UNA_CAIDA: HealthResult = {
  status: 'degraded',
  timestamp: '2026-09-07T13:00:00+00:00',
  integrations: {
    weather: { reachable: true, error: null },
    guardian: { reachable: true, error: null },
    nyt: { reachable: false, error: 'ReadTimeout: timed out' },
  },
};

describe('IndicadorSalud', () => {
  let fixture: ComponentFixture<IndicadorSalud>;
  let http: HttpTestingController;

  /** Monta el indicador y responde al sondeo que lanza al construirse. */
  async function montar(respuesta: HealthResult): Promise<HTMLElement> {
    fixture = TestBed.createComponent(IndicadorSalud);
    http.expectOne('/api/health').flush(respuesta);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  /** Despliega el panel pulsando la pastilla. */
  async function desplegar(html: HTMLElement): Promise<void> {
    html.querySelector<HTMLButtonElement>('.pastilla')?.click();
    await fixture.whenStable();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [IndicadorSalud],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  // Cada sondeo son tres peticiones HTTP reales contra APIs de terceros con
  // cuota, así que un refresco periódico sería caro y no aportaría: es
  // información que cambia despacio.
  it('consulta una sola vez al montar, no en bucle', async () => {
    await montar(TODO_BIEN);

    expect(http.match('/api/health').length).toBe(0);
  });

  it('dice el estado con palabras, no sólo con el color', async () => {
    const html = await montar(TODO_BIEN);

    expect(html.querySelector('.etiqueta')?.textContent).toContain('ok');
    expect(html.querySelector('.salud')?.getAttribute('data-estado')).toBe('ok');
  });

  // El texto va en caja normal en el DOM y las mayúsculas las pone el CSS:
  // muchos lectores de pantalla deletrean las palabras escritas en caja alta.
  it('no escribe la etiqueta en mayúsculas en el DOM', async () => {
    const html = await montar(TODO_BIEN);

    const etiqueta = html.querySelector('.etiqueta')?.textContent?.trim() ?? '';
    expect(etiqueta).not.toBe(etiqueta.toUpperCase());
  });

  it('el panel está plegado hasta que se pide', async () => {
    const html = await montar(TODO_BIEN);

    expect(html.querySelector('.detalle')).toBeNull();
    expect(html.querySelector('.pastilla')?.getAttribute('aria-expanded')).toBe(
      'false',
    );

    await desplegar(html);

    expect(html.querySelector('.detalle')).not.toBeNull();
    expect(html.querySelector('.pastilla')?.getAttribute('aria-expanded')).toBe(
      'true',
    );
  });

  // Sin el detalle por integración, el ámbar no es accionable: dice que algo
  // falla y no cuál. Es el requisito explícito de #147.
  it('al desplegarse enseña qué integración falla y por qué', async () => {
    const html = await montar(UNA_CAIDA);
    await desplegar(html);

    const caidas = [...html.querySelectorAll('.sonda.caida')];
    expect(caidas.length).toBe(1);
    expect(caidas[0].textContent).toContain('New York Times');
    expect(caidas[0].querySelector('.sonda__tecnico')?.textContent).toContain(
      'timed out',
    );
  });

  // Lo accionable es lo que está roto, y con una lista ordenada por nombre
  // podría quedar la última.
  it('pone las caídas delante', async () => {
    const html = await montar(UNA_CAIDA);
    await desplegar(html);

    const nombres = [...html.querySelectorAll('.sonda__nombre')].map(
      (elemento) => elemento.textContent?.trim(),
    );
    expect(nombres[0]).toBe('New York Times');
  });

  // `integrations` es un diccionario abierto: una integración que el frontend
  // no conoce se enseña con su clave en crudo en vez de desaparecer. Mismo
  // criterio que el `@default` de `senal-card`.
  it('enseña en crudo una integración que no sabe nombrar', async () => {
    const html = await montar({
      status: 'ok',
      timestamp: '2026-09-07T13:00:00+00:00',
      integrations: { inventada: { reachable: true, error: null } },
    });
    await desplegar(html);

    expect(html.querySelector('.sonda__nombre')?.textContent).toContain(
      'inventada',
    );
  });

  // Que no conteste la API es distinto de que contesten «todo caído»: en el
  // primer caso no se sabe nada de las APIs externas, y el remedio es otro.
  it('distingue no poder preguntar de que nadie responda', async () => {
    fixture = TestBed.createComponent(IndicadorSalud);
    http.expectOne('/api/health').error(new ProgressEvent('error'), {
      status: 0,
      statusText: 'Unknown Error',
    });
    await fixture.whenStable();

    const html = fixture.nativeElement as HTMLElement;
    expect(html.querySelector('.salud')?.getAttribute('data-estado')).toBe(
      'incomunicado',
    );

    await desplegar(html);
    expect(html.querySelector('.fallo')?.textContent).toContain(
      'No se pudo contactar con la API',
    );
    expect(html.querySelector('.sondas')).toBeNull();
  });

  // Medido el 7-09 parando uvicorn con la interfaz delante: con la API apagada
  // NO llega `status 0`, llega **502**, porque entre el navegador y la API hay
  // siempre un proxy —`proxy.conf.json` hoy, nginx en H4— y quien contesta
  // cuando el destino no está es él. Sin este caso, el mensaje diría que la API
  // no pudo informar de su estado, de un proceso que está apagado.
  it('un 502 del proxy se lee como que no hay API, no como que la API falló', async () => {
    fixture = TestBed.createComponent(IndicadorSalud);
    http.expectOne('/api/health').flush('Bad Gateway', {
      status: 502,
      statusText: 'Bad Gateway',
    });
    await fixture.whenStable();

    const html = fixture.nativeElement as HTMLElement;
    await desplegar(html);

    expect(html.querySelector('.fallo')?.textContent).toContain(
      'No se pudo contactar con la API',
    );
    expect(html.querySelector('.fallo')?.textContent).not.toContain('502');
  });

  it('avisa de que no cubre las señales de análisis', async () => {
    const html = await montar(TODO_BIEN);
    await desplegar(html);

    expect(html.querySelector('.alcance')?.textContent).toContain(
      'Las señales de análisis no se sondean aquí',
    );
  });

  it('vuelve a comprobar a petición', async () => {
    const html = await montar(UNA_CAIDA);
    await desplegar(html);

    html.querySelector<HTMLButtonElement>('.recargar')?.click();
    http.expectOne('/api/health').flush(TODO_BIEN);
    await fixture.whenStable();

    expect(html.querySelector('.salud')?.getAttribute('data-estado')).toBe('ok');
  });
});
