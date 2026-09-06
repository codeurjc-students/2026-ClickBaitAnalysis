import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed, type ComponentFixture } from '@angular/core/testing';

import type { AnalyzeResponse, AnalyzeResult } from '../api/models';
import { AnalisisPage } from './analisis-page';

/** Un análisis con las tres naturalezas de señal y una que no pudo ejecutarse. */
const RESPUESTA: AnalyzeResponse = {
  headline: "10 Amazing Things You Won't Believe",
  content: null,
  signals: [
    {
      name: 'detect_clickbait_lexical',
      label: 'Léxico por reglas',
      status: 'ok',
      dimension: 'form',
      type: 'interpretable',
      is_clickbait: true,
      data: {
        score: 2,
        matches: [
          { category: 'leading_number', cue: '10', span: [0, 2] },
          { category: 'hyperbole', cue: 'Amazing', span: [3, 10] },
        ],
      },
    },
    {
      name: 'detect_clickbait_incoherence',
      label: 'Incoherencia titular ↔ cuerpo',
      status: 'not_applicable',
      dimension: 'deception',
      type: 'hybrid',
      is_clickbait: null,
      detail: 'Requiere el cuerpo o teaser de la noticia.',
    },
    {
      name: 'analyze_sentiment',
      label: 'Tono',
      status: 'ok',
      dimension: 'tone',
      type: 'opaque',
      is_clickbait: null,
      data: { label: 'negative', score: 0.71 },
    },
  ],
  dimensions: [
    {
      dimension: 'form',
      is_clickbait: true,
      contributing: ['detect_clickbait_lexical'],
    },
  ],
  verdict: 'stylistic_clickbait',
};

/**
 * Lo que devuelve `/analyze` de verdad desde #133: el analisis envuelto, con el
 * id de su entrada del historial al lado. La pagina lo abre y guarda las dos
 * mitades por separado.
 */
const SOBRE: AnalyzeResult = { id: 7, analysis: RESPUESTA };

describe('AnalisisPage', () => {
  let fixture: ComponentFixture<AnalisisPage>;
  let pagina: AnalisisPage;
  let http: HttpTestingController;

  const html = () => fixture.nativeElement as HTMLElement;

  /** El `(ngSubmit)` de Angular escucha el `submit` nativo del formulario. */
  const enviar = async () => {
    html().querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AnalisisPage],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(AnalisisPage);
    pagina = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => http.verify());

  it('arranca mostrando el formulario', () => {
    expect(html().querySelector('form')).not.toBeNull();
    expect(html().querySelector('.veredicto')).toBeNull();
  });

  // El caso que justifica `markAsTouched()`: sin él, pulsar Analizar con el
  // campo vacío no haría NADA visible y el botón parecería roto.
  it('con el titular en blanco no llama a la API y avisa en pantalla', async () => {
    pagina.formulario.controls.headline.setValue('   ');
    await enviar();

    http.expectNone('/api/analyze');
    expect(html().querySelector('.error-campo')?.textContent).toContain(
      'no puede estar en blanco',
    );
    expect(html().querySelector('#headline')?.getAttribute('aria-invalid')).toBe(
      'true',
    );
  });

  it('pinta el veredicto y una pastilla por señal', async () => {
    pagina.formulario.controls.headline.setValue('Un titular');
    await enviar();

    http.expectOne('/api/analyze').flush(SOBRE);
    await fixture.whenStable();

    expect(html().querySelector('.veredicto h2')?.textContent).toContain(
      'Clickbait de forma',
    );
    const pastillas = html().querySelectorAll('.pastilla');
    expect(pastillas.length).toBe(3);
    // El tipo va al atributo, y de ahí sale el color.
    expect(pastillas[1].getAttribute('data-tipo')).toBe('hybrid');
  });

  it('resalta sobre el titular las pistas que encontró el léxico', async () => {
    pagina.formulario.controls.headline.setValue('Un titular');
    await enviar();

    http.expectOne('/api/analyze').flush(SOBRE);
    await fixture.whenStable();

    const marcas = [...html().querySelectorAll('mark[data-categoria]')];
    const resaltado = marcas.map((marca) => marca.textContent);
    expect(resaltado).toContain('10');
    expect(resaltado).toContain('Amazing');
  });

  // Una señal sin resultado no se esconde: se muestra diciendo por qué.
  it('muestra el estado de las señales que no votaron', async () => {
    pagina.formulario.controls.headline.setValue('Un titular');
    await enviar();

    http.expectOne('/api/analyze').flush(SOBRE);
    await fixture.whenStable();

    const textos = [...html().querySelectorAll('.pastilla')].map(
      (pastilla) => pastilla.textContent ?? '',
    );
    expect(textos[1]).toContain('no aplicable');
    expect(textos[2]).toContain('no vota');
  });

  it('explica el fallo cuando la API no responde', async () => {
    pagina.formulario.controls.headline.setValue('Un titular');
    await enviar();

    // `status 0` no es HTTP: es que no contestó nadie.
    http
      .expectOne('/api/analyze')
      .error(new ProgressEvent('error'), { status: 0 });
    await fixture.whenStable();

    expect(html().querySelector('.error')?.textContent).toContain(
      'No se pudo contactar con la API',
    );
    expect(html().querySelector('form')).not.toBeNull();
  });

  it('«Nuevo análisis» devuelve el formulario vacío', async () => {
    pagina.formulario.controls.headline.setValue('Un titular');
    await enviar();
    http.expectOne('/api/analyze').flush(SOBRE);
    await fixture.whenStable();

    pagina.nuevoAnalisis();
    await fixture.whenStable();

    expect(html().querySelector('.veredicto')).toBeNull();
    expect(html().querySelector('form')).not.toBeNull();
    expect(pagina.formulario.controls.headline.value).toBe('');
  });

  // ----- Recuperar un análisis guardado (/analisis/:id) -----

  /**
   * La entrada tal como la sirve `GET /history/{id}`: el payload es la
   * respuesta ENTERA de entonces, que es lo que permite no reejecutar.
   */
  const entradaGuardada = (payload: unknown) => ({
    id: 29,
    created_at: '2026-09-03T09:10:53.904600Z',
    kind: 'analysis',
    origin: 'form',
    headline: RESPUESTA.headline,
    verdict: RESPUESTA.verdict,
    status: 'ok',
    payload,
  });

  const abrirGuardado = async (payload: unknown, id = '29') => {
    fixture.componentRef.setInput('id', id);
    await fixture.whenStable();
    http.expectOne(`/api/history/${id}`).flush(entradaGuardada(payload));
    await fixture.whenStable();
  };

  it('con un id en la ruta recupera el análisis en vez de reejecutarlo', async () => {
    await abrirGuardado(RESPUESTA);

    // Lo importante es lo que NO pasa: nadie ha llamado a /analyze.
    http.expectNone('/api/analyze');
    expect(html().querySelector('.veredicto')?.textContent).toContain(
      'Clickbait de forma',
    );
    expect(html().querySelectorAll('app-senal-card').length).toBe(3);
  });

  it('dice que lo que se ve viene del historial, y cuándo se guardó', async () => {
    await abrirGuardado(RESPUESTA);

    expect(html().querySelector('.barra__etiqueta')?.textContent).toContain(
      'Recuperado del historial',
    );
    expect(html().querySelector('.barra__etiqueta')?.textContent).toContain(
      '2026',
    );
  });

  // Una entrada de antes de #133 no trae `label`, y una de antes de #134 trae
  // el veredicto en castellano. Se pinta igual: esconder el análisis entero por
  // una etiqueta sería peor que enseñar la palabra vieja.
  it('pinta un análisis guardado con el contrato anterior', async () => {
    await abrirGuardado({
      headline: 'Un titular de antes',
      signals: [
        {
          name: 'detect_clickbait_lexical',
          status: 'ok',
          dimension: 'forma',
          type: 'interpretable',
          is_clickbait: true,
        },
      ],
      dimensions: [{ dimension: 'forma', is_clickbait: true }],
      verdict: 'ambiguo',
    });

    // Sin `label`, el nombre cae al identificador de la herramienta.
    expect(html().textContent).toContain('detect_clickbait_lexical');
    expect(html().querySelector('.veredicto')?.textContent).toContain('ambiguo');
  });

  // El 404 aquí no es una avería: la retención borra las entradas viejas, así
  // que un enlace guardado deja de existir por funcionamiento normal.
  it('explica el 404 por la retención, no como fallo', async () => {
    fixture.componentRef.setInput('id', '999999');
    await fixture.whenStable();
    http
      .expectOne('/api/history/999999')
      .flush({ detail: 'no existe' }, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();

    expect(html().querySelector('.error')?.textContent).toContain('retenci');
    expect(html().querySelector('.veredicto')).toBeNull();
  });

  it('una entrada que no es un análisis se dice, no se pinta a medias', async () => {
    await abrirGuardado({ tool: 'get_nyt_news', status: 'ok', data: {} });

    expect(html().querySelector('.error')?.textContent).toContain(
      'no tiene forma de an',
    );
    expect(html().querySelector('.veredicto')).toBeNull();
  });
});
