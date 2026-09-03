import { TestBed, type ComponentFixture } from '@angular/core/testing';

import type { SignalResult } from '../api/models';
import { SenalCard } from './senal-card';

const LEXICA: SignalResult = {
  name: 'detect_clickbait_lexical',
  status: 'ok',
  dimension: 'forma',
  type: 'interpretable',
  is_clickbait: true,
  data: {
    score: 2,
    matches: [
      { category: 'leading_number', cue: '10', span: [0, 2] },
      { category: 'hyperbole', cue: 'Amazing', span: [3, 10] },
    ],
  },
};

const OPACA: SignalResult = {
  name: 'detect_clickbait',
  status: 'ok',
  dimension: 'forma',
  type: 'opaco',
  is_clickbait: true,
  data: { label: 'clickbait', score: 0.83 },
};

const CAIDA: SignalResult = {
  name: 'detect_clickbait',
  status: 'error',
  dimension: 'forma',
  type: 'opaco',
  data: null,
  detail: 'HTTP error: 400 - Model not supported by provider hf-inference',
};

const DESCONOCIDA: SignalResult = {
  name: 'una_senal_futura',
  status: 'ok',
  dimension: 'forma',
  type: 'interpretable',
  is_clickbait: false,
  data: { algo: 'que nadie ha previsto' },
};

describe('SenalCard', () => {
  let fixture: ComponentFixture<SenalCard>;

  const montar = async (senal: SignalResult) => {
    fixture = TestBed.createComponent(SenalCard);
    fixture.componentRef.setInput('senal', senal);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [SenalCard] }).compileComponents();
  });

  it('la interpretable nace desplegada y la opaca plegada', async () => {
    const interpretable = await montar(LEXICA);
    expect(interpretable.querySelector('.cabecera')?.getAttribute('aria-expanded')).toBe(
      'true',
    );

    const opaca = await montar(OPACA);
    expect(opaca.querySelector('.cabecera')?.getAttribute('aria-expanded')).toBe(
      'false',
    );
  });

  // El hueco que destapó ejecutar la pantalla de verdad: una pastilla que decía
  // «error» y se callaba el motivo.
  it('una señal caída explica el motivo aunque esté plegada', async () => {
    const html = await montar(CAIDA);

    expect(html.querySelector('.cabecera')?.getAttribute('aria-expanded')).toBe(
      'false',
    );
    expect(html.querySelector('.motivo')?.textContent).toContain(
      'Model not supported',
    );
  });

  it('el léxico pinta una pastilla por pista, con su categoría legible', async () => {
    const html = await montar(LEXICA);

    const pistas = [...html.querySelectorAll('.pistas li')].map(
      (elemento) => elemento.textContent?.trim() ?? '',
    );
    expect(pistas).toEqual(['número inicial: 10', 'hipérbole: Amazing']);
  });

  it('al alternar la cabecera se despliega la opaca', async () => {
    const html = await montar(OPACA);

    html.querySelector<HTMLButtonElement>('.cabecera')!.click();
    await fixture.whenStable();

    expect(html.querySelector('.resumen')?.textContent).toContain('clickbait');
    expect(html.querySelector('.resumen')?.textContent).toContain('0,83');
  });

  // Una señal que nadie ha previsto no desaparece: enseña su JSON.
  it('una señal desconocida cae en el JSON crudo', async () => {
    const html = await montar(DESCONOCIDA);

    expect(html.querySelector('.crudo')?.textContent).toContain(
      'que nadie ha previsto',
    );
  });
});
