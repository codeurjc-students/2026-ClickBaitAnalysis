import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
  type TestRequest,
} from '@angular/common/http/testing';
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import type { HistoryResult } from '../api/models';
import { HistorialPage } from './historial-page';

/**
 * Copiado de lo que devuelve el historial local de verdad, incluidos sus
 * defectos: la entrada 28 tiene el veredicto en castellano porque se guardó
 * antes de #134, cuando las claves del dominio llevaban diacríticos.
 */
const PAGINA: HistoryResult = {
  items: [
    {
      id: 30,
      created_at: '2026-09-06T09:34:48.696749Z',
      kind: 'tool',
      origin: 'api',
      tool: 'detect_clickbait_lexical',
      headline: '10 Amazing Things You Won\'t Believe',
      status: 'ok',
      payload: { tool: 'detect_clickbait_lexical', status: 'ok', data: { score: 4 } },
    },
    {
      id: 29,
      created_at: '2026-09-03T09:10:53.904600Z',
      kind: 'analysis',
      origin: 'api',
      headline: 'Why skateboarding is more than a sport in Nigeria',
      verdict: 'factual',
      status: 'ok',
      payload: {},
    },
    {
      id: 28,
      created_at: '2026-09-03T09:09:13.609143Z',
      kind: 'analysis',
      origin: 'api',
      headline: 'She fled Iran. America sent her to Africa',
      verdict: 'ambiguo',
      status: 'ok',
      payload: {},
    },
  ],
  total: 29,
  limit: 20,
  offset: 0,
  retention: { max_entries: 1000, max_days: 30 },
};

const VACIA: HistoryResult = { ...PAGINA, items: [], total: 0 };

describe('HistorialPage', () => {
  let fixture: ComponentFixture<HistorialPage>;
  let http: HttpTestingController;

  const pedida = (): TestRequest =>
    http.expectOne((candidata) => candidata.url === '/api/history');

  const montar = async (pagina: HistoryResult = PAGINA) => {
    fixture = TestBed.createComponent(HistorialPage);
    pedida().flush(pagina);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  };

  const elegir = async (raiz: HTMLElement, selector: string, valor: string) => {
    const control = raiz.querySelector<HTMLSelectElement>(selector);
    if (control) {
      control.value = valor;
      control.dispatchEvent(new Event('change'));
    }
    await fixture.whenStable();
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        // La plantilla usa `routerLink` para volver a un análisis.
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('pide la primera página al montar y pinta una fila por entrada', async () => {
    const raiz = await montar();

    expect(raiz.querySelectorAll('tbody tr').length).toBe(3);
    expect(raiz.textContent).toContain('Mostrando 1–20 de 29');
  });

  it('enseña la herramienta de una ejecución y el titular de un análisis', async () => {
    const raiz = await montar();

    expect(raiz.querySelector('code')?.textContent).toBe('detect_clickbait_lexical');
    expect(raiz.textContent).toContain('Why skateboarding is more than a sport');
  });

  // Los titulares son ingleses por contrato y la página está en castellano.
  it('marca el idioma de los titulares analizados', async () => {
    const raiz = await montar();

    expect(raiz.querySelector('.titular')?.getAttribute('lang')).toBe('en');
  });

  // #134 pasó las claves a inglés. Una entrada anterior se pinta con lo que
  // tiene, no se esconde: el vocabulario cae al valor crudo.
  it('pinta un veredicto anterior al cambio de claves', async () => {
    const raiz = await montar();

    expect(raiz.textContent).toContain('Factual');
    expect(raiz.textContent).toContain('ambiguo');
  });

  it('un análisis enlaza a su propia ruta', async () => {
    const raiz = await montar();

    const enlace = raiz.querySelector<HTMLAnchorElement>('tbody a');
    expect(enlace?.getAttribute('href')).toBe('/analisis/29');
  });

  it('una ejecución suelta despliega su salida en crudo', async () => {
    const raiz = await montar();

    raiz.querySelector<HTMLButtonElement>('tbody button')?.click();
    await fixture.whenStable();

    expect(raiz.querySelector('.crudo')?.textContent).toContain('score');
  });

  it('la paginación pide el siguiente tramo', async () => {
    const raiz = await montar();

    const botones = raiz.querySelectorAll<HTMLButtonElement>('.paginacion button');
    expect(botones[0].disabled).toBe(true);
    botones[1].click();
    await fixture.whenStable();

    expect(pedida().request.params.get('offset')).toBe('20');
  });

  // Filtrar desde la página 3 sin volver al principio deja la pantalla vacía
  // sobre un resultado que sí tiene entradas, y parece que no hay nada.
  it('cambiar un filtro vuelve a la primera página', async () => {
    const raiz = await montar();

    raiz.querySelectorAll<HTMLButtonElement>('.paginacion button')[1].click();
    await fixture.whenStable();
    pedida().flush({ ...PAGINA, offset: 20 });
    await fixture.whenStable();

    await elegir(raiz, '#filtro-kind', 'analysis');

    const peticion = pedida();
    expect(peticion.request.params.get('kind')).toBe('analysis');
    expect(peticion.request.params.get('offset')).toBe('0');
    peticion.flush(PAGINA);
  });

  // Sale de la respuesta y no de constantes de aquí: cableado, prometería 30
  // días el día que cambie el `.env`.
  //
  // Y `1000` sin punto no es un descuido: en es-ES la agrupación de millares
  // NO empieza hasta cinco dígitos (medido: 1000 -> "1000", 10000 -> "10.000").
  // En en-US sí se agrupa desde cuatro, que es de donde viene la costumbre.
  it('explica la retención con los números del backend', async () => {
    const raiz = await montar();

    expect(raiz.textContent).toContain('1000 entradas');
    expect(raiz.textContent).toContain('30 días');
  });

  it('sin entradas lo dice, en vez de dejar una tabla vacía', async () => {
    const raiz = await montar(VACIA);

    expect(raiz.querySelector('table')).toBeNull();
    expect(raiz.textContent).toContain('No hay ninguna entrada');
  });

  it('explica el fallo cuando el historial no se puede leer', async () => {
    fixture = TestBed.createComponent(HistorialPage);
    pedida().flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('La API falló al leer el historial');
  });
});
