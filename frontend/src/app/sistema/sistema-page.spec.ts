import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed, type ComponentFixture } from '@angular/core/testing';

import type { CatalogResult } from '../api/models';
import { SistemaPage } from './sistema-page';

/**
 * Un catálogo con las tres cosas que la pantalla tiene que saber contar: un
 * servidor caído, herramientas de categorías distintas y una señal con ficha.
 */
const CATALOGO: CatalogResult = {
  servers: [
    { url: 'http://127.0.0.1:8010/mcp', name: 'tfg', status: 'ok', tool_count: 3 },
    {
      url: 'http://127.0.0.1:8011/mcp',
      status: 'unreachable',
      tool_count: 0,
      detail: 'ConnectError: All connection attempts failed',
    },
  ],
  tools: [
    {
      name: 'detect_clickbait_lexical',
      description: 'Detecta clickbait por vocabulario, con reglas visibles.',
      input_schema: {
        type: 'object',
        properties: { headline: { type: 'string' } },
        required: ['headline'],
      },
      category: 'Señales de análisis',
      integration: 'nlp',
      server: 'tfg',
      model_card: {
        name: 'Léxico por reglas',
        task: 'Marca los cues de clickbait que aparecen en el titular.',
        model_id: null,
        type: 'interpretable',
        dimension: 'form',
        limitations: ['Sólo inglés.', 'No entiende el contexto.'],
      },
    },
    {
      name: 'get_nyt_news',
      description: 'Trae titulares del New York Times.',
      input_schema: {
        type: 'object',
        properties: {
          days: { type: 'integer', minimum: 1, maximum: 30, default: 7 },
        },
      },
      category: 'Fuentes de contenido',
      integration: 'nyt',
      server: 'tfg',
    },
    {
      name: 'describe_models',
      description: 'Devuelve las fichas de los modelos.',
      input_schema: { type: 'object', properties: {} },
      category: 'Utilidades',
      integration: 'nlp',
      server: 'tfg',
    },
  ],
  degraded: true,
};

describe('SistemaPage', () => {
  let fixture: ComponentFixture<SistemaPage>;
  let http: HttpTestingController;

  const montar = async (catalogo: CatalogResult = CATALOGO) => {
    fixture = TestBed.createComponent(SistemaPage);
    // La petición sale en el constructor: la pantalla no sirve de nada vacía.
    http.expectOne('/api/tools').flush(catalogo);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  };

  const escribir = async (raiz: HTMLElement, selector: string, valor: string) => {
    const control = raiz.querySelector<HTMLInputElement | HTMLSelectElement>(selector);
    if (control) {
      control.value = valor;
      const evento = control instanceof HTMLSelectElement ? 'change' : 'input';
      control.dispatchEvent(new Event(evento));
    }
    await fixture.whenStable();
  };

  const desplegar = async (raiz: HTMLElement, indice: number) => {
    raiz.querySelectorAll<HTMLButtonElement>('.tool__cabecera')[indice]?.click();
    await fixture.whenStable();
  };

  const ejecutar = async (raiz: HTMLElement) => {
    const boton = raiz.querySelector<HTMLButtonElement>(
      'app-esquema-form button[type="submit"]',
    );
    boton?.click();
    await fixture.whenStable();
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  // Un servidor caído sale en la lista con su motivo: la alternativa —una lista
  // más corta— no distingue «no hay» de «no contestó».
  it('enseña los servidores, incluido el que no respondió', async () => {
    const raiz = await montar();

    expect(raiz.textContent).toContain('tfg');
    expect(raiz.textContent).toContain('no responde');
    expect(raiz.textContent).toContain('ConnectError');
    expect(raiz.querySelector('[data-estado="unreachable"]')).not.toBeNull();
  });

  it('avisa de que el catálogo está incompleto', async () => {
    const raiz = await montar();

    expect(raiz.textContent).toContain('el catálogo está incompleto');
  });

  // Las categorías del desplegable salen del catálogo. Una tool con una
  // categoría nueva la ofrecería sin tocar esta pantalla (R1.9).
  it('ofrece como filtro las categorías que trae el catálogo', async () => {
    const raiz = await montar();

    const opciones = [...raiz.querySelectorAll('#categoria option')].map((opcion) =>
      opcion.textContent?.trim(),
    );
    expect(opciones).toEqual([
      'Todas',
      'Fuentes de contenido',
      'Señales de análisis',
      'Utilidades',
    ]);
  });

  it('filtra por categoría', async () => {
    const raiz = await montar();

    await escribir(raiz, '#categoria', 'Utilidades');

    expect(raiz.querySelectorAll('.tool').length).toBe(1);
    expect(raiz.textContent).toContain('describe_models');
  });

  it('busca por nombre de herramienta', async () => {
    const raiz = await montar();

    await escribir(raiz, '#busqueda', 'nyt');

    expect(raiz.querySelectorAll('.tool').length).toBe(1);
    expect(raiz.textContent).toContain('get_nyt_news');
  });

  // La descripción es la docstring que lee el LLM, y ahí está lo que la
  // herramienta hace de verdad: buscar sólo por nombre dejaría fuera lo útil.
  it('busca también en la descripción, sin distinguir mayúsculas', async () => {
    const raiz = await montar();

    await escribir(raiz, '#busqueda', 'VOCABULARIO');

    expect(raiz.querySelectorAll('.tool').length).toBe(1);
    expect(raiz.textContent).toContain('detect_clickbait_lexical');
  });

  it('ejecuta la herramienta desplegada y enseña su salida', async () => {
    const raiz = await montar();

    await desplegar(raiz, 1);
    await ejecutar(raiz);

    const peticion = http.expectOne('/api/tools/get_nyt_news/execute');
    // El `days: 7` no lo escribió nadie: sale del `default` del esquema.
    expect(peticion.request.body).toEqual({ arguments: { days: 7 } });

    peticion.flush({
      tool: 'get_nyt_news',
      server: 'tfg',
      status: 'ok',
      data: { articles: [] },
    });
    await fixture.whenStable();

    expect(raiz.querySelector('.crudo')?.textContent).toContain('articles');
  });

  // 200 con `status: error`: la herramienta falló, la petición no. Se enseña su
  // motivo, que es lo único accionable.
  it('enseña el motivo cuando la herramienta falla', async () => {
    const raiz = await montar();

    await desplegar(raiz, 1);
    await ejecutar(raiz);

    http.expectOne('/api/tools/get_nyt_news/execute').flush({
      tool: 'get_nyt_news',
      server: 'tfg',
      status: 'error',
      detail: 'La API de NYT respondió 503.',
    });
    await fixture.whenStable();

    expect(raiz.textContent).toContain('La herramienta falló');
    expect(raiz.textContent).toContain('503');
  });

  // El 504 NO dice que la herramienta fallara: dice que se agotó la espera, y
  // puede haber terminado bien (#113). El mensaje tiene que distinguirlo.
  it('explica el 504 como espera agotada, no como fallo', async () => {
    const raiz = await montar();

    await desplegar(raiz, 1);
    await ejecutar(raiz);

    http
      .expectOne('/api/tools/get_nyt_news/execute')
      .flush({ detail: 'timeout' }, { status: 504, statusText: 'Gateway Timeout' });
    await fixture.whenStable();

    expect(raiz.textContent).toContain('Se agotó la espera');
  });

  it('enseña la ficha de modelo de las señales, con sus límites', async () => {
    const raiz = await montar();

    const ficha = raiz.querySelector('.ficha');
    expect(ficha?.textContent).toContain('Léxico por reglas');
    expect(ficha?.textContent).toContain('Forma');
    // El `null` del `model_id` es información, no un hueco.
    expect(ficha?.textContent).toContain('código propio');
    expect(ficha?.querySelectorAll('li').length).toBe(2);
  });

  it('explica el fallo cuando el catálogo no se puede cargar', async () => {
    fixture = TestBed.createComponent(SistemaPage);
    http
      .expectOne('/api/tools')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('La API falló al construir el catálogo');
  });
});
