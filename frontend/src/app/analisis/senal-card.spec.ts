import { TestBed, type ComponentFixture } from '@angular/core/testing';

import type { SignalResult } from '../api/models';
import type { SenalGuardada } from './formas';
import { SenalCard } from './senal-card';

const LEXICA: SignalResult = {
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
};

const OPACA: SignalResult = {
  name: 'detect_clickbait',
  label: 'RoBERTa dedicado',
  status: 'ok',
  dimension: 'form',
  type: 'opaque',
  is_clickbait: true,
  data: { label: 'clickbait', score: 0.83 },
};

const CAIDA: SignalResult = {
  name: 'detect_clickbait',
  label: 'RoBERTa dedicado',
  status: 'error',
  dimension: 'form',
  type: 'opaque',
  data: null,
  detail: 'HTTP error: 400 - Model not supported by provider hf-inference',
};

/**
 * La incoherencia sin cuerpo de noticia. Su `detail` no es un volcado: ya es la
 * frase que hay que leer, y por eso se trata distinto que un error.
 */
const NO_APLICABLE: SignalResult = {
  name: 'detect_clickbait_incoherence',
  label: 'MiniLM-L6-v2 (embeddings de frase)',
  status: 'not_applicable',
  dimension: 'deception',
  type: 'hybrid',
  is_clickbait: null,
  detail: 'Requiere el cuerpo o teaser de la noticia.',
};

const DESCONOCIDA: SignalResult = {
  name: 'una_senal_futura',
  label: 'Una señal futura',
  status: 'ok',
  dimension: 'form',
  type: 'interpretable',
  is_clickbait: false,
  data: { algo: 'que nadie ha previsto' },
};

describe('SenalCard', () => {
  let fixture: ComponentFixture<SenalCard>;

  // La forma ANCHA, no el contrato: esta tarjeta pinta también lo guardado
  // con versiones anteriores, y es lo que recibe de verdad desde #129.
  const montar = async (senal: SenalGuardada) => {
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

  // Medido en #130 sobre el análisis 31: la tarjeta de una opaca CAÍDA tenía el
  // mismo borde que la de una opaca sana, `rgb(184,84,80)`, porque el color
  // lleva el TIPO. Lo único que las distinguía era leer la palabra «error».
  it('una señal caída se apaga, y una sana no', async () => {
    const caida = await montar(CAIDA);
    expect(caida.querySelector('.tarjeta')?.classList).toContain('atenuada');

    const sana = await montar(LEXICA);
    expect(sana.querySelector('.tarjeta')?.classList).not.toContain('atenuada');
  });

  // Apagarla no puede borrar de que TIPO era: eso sigue siendo cierto, sólo
  // deja de competir por la atención.
  it('apagada, la tarjeta sigue diciendo su tipo', async () => {
    const raiz = await montar(CAIDA);

    expect(raiz.querySelector('.badge')?.textContent).toContain('opaque');
    expect(raiz.querySelector('.tarjeta')?.getAttribute('data-tipo')).toBe('opaque');
  });

  // `not_applicable` tampoco votó, así que también se apaga. Y se comprueba con
  // el valor ANTIGUO —`no_aplicable`, de antes de #134— porque el historial los
  // guarda: `funciono` compara contra `ok`, no contra la lista de fallos.
  it('una señal no aplicable se apaga, también con la clave vieja', async () => {
    // Tipado con la forma ANCHA, no con el contrato: `no_aplicable` no es un
    // `SignalStatus` válido hoy —lo dice el compilador— y ése es justo el
    // caso, una fila guardada antes de #134.
    const vieja: SenalGuardada = { ...CAIDA, status: 'no_aplicable' };

    const raiz = await montar(vieja);

    expect(raiz.querySelector('.tarjeta')?.classList).toContain('atenuada');
  });

  // R6.7 pide que el error del backend llegue entendible y no como un volcado.
  // El `detail` de esta señal es literalmente
  // «HTTP error: 400 - {"error":"Model not supported by provider hf-inference"}»,
  // así que se antepone la frase que se entiende y el volcado se queda marcado
  // como técnico: esconderlo dejaría sin nada a quien tenga que diagnosticar.
  it('una señal caída explica primero, y vuelca después', async () => {
    const raiz = await montar(CAIDA);

    expect(raiz.querySelector('.motivo__resumen')?.textContent).toContain(
      'no llegó a ejecutarse',
    );
    expect(raiz.querySelector('.motivo__tecnico')?.textContent).toContain(
      'hf-inference',
    );
  });

  // En `not_applicable` el detalle YA es la frase que se entiende, así que no
  // se le antepone nada: sería ruido sobre algo que no ha fallado.
  it('una no aplicable usa su detalle tal cual', async () => {
    const raiz = await montar(NO_APLICABLE);

    expect(raiz.querySelector('.motivo__resumen')).toBeNull();
    expect(raiz.querySelector('.motivo')?.textContent).toContain(
      'Requiere el cuerpo',
    );
  });
});
