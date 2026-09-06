import type { AnalyzeResponse } from '../api/models';
import { comoAnalisis } from './formas';

/**
 * Un análisis de HOY, tipado con el contrato a propósito: si algún día
 * `AnalyzeResponse` deja de encajar en `AnalisisGuardado`, esto no compila. Es
 * lo que sostiene que la misma vista sirva para lo recién hecho y lo guardado.
 */
const DE_HOY: AnalyzeResponse = {
  headline: '10 Amazing Things You Won\'t Believe',
  content: null,
  signals: [
    {
      name: 'detect_clickbait_lexical',
      label: 'Léxico por reglas',
      status: 'ok',
      dimension: 'form',
      type: 'interpretable',
      is_clickbait: true,
      data: { score: 4 },
    },
  ],
  dimensions: [{ dimension: 'form', is_clickbait: true }],
  verdict: 'stylistic_clickbait',
};

describe('comoAnalisis', () => {
  it('lee un análisis recién hecho', () => {
    expect(comoAnalisis(DE_HOY)).toBe(DE_HOY);
  });

  // `label` se añadió en #133. Exigirlo mandaría a JSON crudo todo lo guardado
  // antes, que es justo lo que el historial existe para poder enseñar.
  it('lee una entrada de antes de que existiera `label`', () => {
    const guardado = {
      headline: 'Un titular',
      signals: [
        {
          name: 'detect_clickbait_lexical',
          status: 'ok',
          dimension: 'forma',
          type: 'interpretable',
        },
      ],
      dimensions: [{ dimension: 'forma' }],
      verdict: 'clickbait_de_forma',
    };

    expect(comoAnalisis(guardado)?.signals[0].label).toBeUndefined();
  });

  // #134 pasó las claves del dominio a inglés. Rechazar los valores viejos
  // escondería el análisis entero por una etiqueta; el vocabulario ya cae al
  // valor crudo cuando no lo conoce.
  it('no rechaza un veredicto de antes de que las claves fueran inglés', () => {
    const antiguo = { ...DE_HOY, verdict: 'engañoso' };

    expect(comoAnalisis(antiguo)?.verdict).toBe('engañoso');
  });

  // El historial mezcla análisis y ejecuciones sueltas. Se distingue por la
  // FORMA y no por el campo `kind`: uno dice lo que se pidió, la otra lo que
  // se puede pintar.
  it('una ejecución suelta no es un análisis', () => {
    const ejecucion = {
      tool: 'get_nyt_news',
      server: 'tfg-mcp-server',
      status: 'ok',
      data: { articles: [] },
    };

    expect(comoAnalisis(ejecucion)).toBeNull();
  });

  it('sin las dos listas no hay análisis', () => {
    expect(comoAnalisis({ ...DE_HOY, signals: 'ninguna' })).toBeNull();
    expect(comoAnalisis({ ...DE_HOY, dimensions: undefined })).toBeNull();
  });

  it('una señal a medias invalida el análisis, y no revienta con nulos', () => {
    expect(comoAnalisis({ ...DE_HOY, signals: [null] })).toBeNull();
    expect(
      comoAnalisis({ ...DE_HOY, signals: [{ name: 'sin_estado' }] }),
    ).toBeNull();
  });

  it('lo que no tiene forma de objeto devuelve null', () => {
    expect(comoAnalisis(null)).toBeNull();
    expect(comoAnalisis('un texto')).toBeNull();
    expect(comoAnalisis({})).toBeNull();
  });
});
