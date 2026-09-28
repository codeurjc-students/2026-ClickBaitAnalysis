import type { ChatJob, PasoHerramienta, SignalResult } from '../api/models';
import {
  comoNoticias,
  duracionLegible,
  esperaDe,
  ESPERA_LARGA_MS,
  historialQueCabe,
  usoHerramientas,
  vistaDePaso,
  type Intercambio,
} from './conversacion';

/** Un paso de herramienta que funcionó, con el `data` que se diga. */
function herramienta(nombre: string, datos: unknown, senal: SignalResult | null = null): PasoHerramienta {
  return {
    kind: 'tool',
    round: 1,
    name: nombre,
    arguments: {},
    status: 'ok',
    data: datos,
    error: null,
    server: 'http://mcp:8765/mcp',
    duration_s: 0.3,
    signal: senal,
  };
}

const SENAL: SignalResult = {
  name: 'detect_clickbait_lexical',
  label: 'Léxico por reglas',
  status: 'ok',
  dimension: 'form',
  type: 'interpretable',
  is_clickbait: true,
  data: { score: 1, is_clickbait: true, matches: [], headline: 'x' },
};

/** Un intercambio terminado, con la respuesta que se diga. */
function terminado(pregunta: string, respuesta: string): Intercambio {
  const trabajo: ChatJob = {
    id: pregunta,
    status: 'done',
    created_at: '2026-09-28T10:00:00Z',
    steps: [],
    result: { status: 'answered', answer: respuesta, detail: null, rounds: 1, total_s: 3 },
  };
  return { pregunta, trabajo, error: null, enviadaEl: 0, leidaEl: 3000 };
}

describe('vistaDePaso', () => {
  it('una vuelta del modelo dice qué pidió', () => {
    const vista = vistaDePaso({
      kind: 'model',
      round: 1,
      content: '',
      tool_calls: ['detect_clickbait', 'get_nyt_news'],
      metrics: { prompt_tokens: 3700, output_tokens: 40, load_s: 0, total_s: 4 },
    });
    expect(vista.herramienta).toBeNull();
    expect(vista.pide).toEqual(['detect_clickbait', 'get_nyt_news']);
  });

  // La tarjeta la calcula el backend con la regla del análisis (#191): aquí
  // sólo se usa, no se decide qué es clickbait.
  it('una señal suelta se pinta con la tarjeta que trae', () => {
    const vista = vistaDePaso(herramienta('detect_clickbait_lexical', SENAL.data, SENAL));
    expect(vista.senal).toEqual(SENAL);
    expect(vista.crudo).toBeNull();
  });

  it('un análisis entero se pinta como análisis', () => {
    const analisis = {
      headline: 'Top 5 Secrets',
      content: null,
      signals: [],
      dimensions: [],
      verdict: 'stylistic_clickbait',
    };
    const vista = vistaDePaso(herramienta('analyze_headline', analisis));
    expect(vista.analisis?.headline).toBe('Top 5 Secrets');
  });

  it('una lista de noticias se pinta como noticias, por su forma', () => {
    const vista = vistaDePaso(
      herramienta('get_guardian_news', {
        result: [{ title: 'A headline', url: 'https://x', date: '2026-09-27T10:00:00Z' }],
      }),
    );
    expect(vista.noticias).toEqual([
      { title: 'A headline', url: 'https://x', date: '2026-09-27T10:00:00Z' },
    ]);
  });

  // Lo que no encaja se ve igual, en crudo: omitirlo sería mentir sobre lo
  // que se consultó.
  it('lo que no se reconoce se enseña en crudo', () => {
    const vista = vistaDePaso(herramienta('get_forecast', { result: 'Soleado' }));
    expect(vista.crudo).toContain('Soleado');
    expect(vista.senal ?? vista.analisis ?? vista.noticias).toBeNull();
  });

  it('una herramienta que falló dice por qué', () => {
    const vista = vistaDePaso({
      ...herramienta('get_nyt_news', null),
      status: 'error',
      error: 'La API externa respondió HTTP 429 Too Many Requests.',
    });
    expect(vista.error).toContain('429');
  });
});

describe('comoNoticias', () => {
  it('rechaza una lista de otra cosa, como las fichas de describe_models', () => {
    expect(comoNoticias({ result: [{ name: 'Léxico', task: '…' }] })).toBeNull();
  });

  it('rechaza lo que no es una lista', () => {
    expect(comoNoticias({ result: 'texto' })).toBeNull();
    expect(comoNoticias(null)).toBeNull();
  });
});

describe('historialQueCabe', () => {
  it('manda el texto de los intercambios terminados, en orden', () => {
    const historial = historialQueCabe(
      [terminado('¿Es clickbait?', 'Sí.'), terminado('¿Y este?', 'No.')],
      4000,
    );
    expect(historial).toEqual([
      { role: 'user', content: '¿Es clickbait?' },
      { role: 'assistant', content: 'Sí.' },
      { role: 'user', content: '¿Y este?' },
      { role: 'assistant', content: 'No.' },
    ]);
  });

  // Lo que no terminó con respuesta no se manda: el modelo leería una
  // pregunta sin contestar como si siguiera pendiente.
  it('se salta los intercambios sin respuesta', () => {
    const fallido: Intercambio = {
      pregunta: '¿Hola?',
      trabajo: null,
      error: 'Falló.',
      enviadaEl: 0,
      leidaEl: null,
    };
    expect(historialQueCabe([fallido, terminado('¿Y este?', 'No.')], 4000)).toEqual([
      { role: 'user', content: '¿Y este?' },
      { role: 'assistant', content: 'No.' },
    ]);
  });

  it('quita los intercambios más antiguos, por parejas, hasta que cabe', () => {
    const historial = historialQueCabe(
      [terminado('uno', 'x'.repeat(10)), terminado('dos', 'y'.repeat(10))],
      15, // la segunda pareja son 13 caracteres; las dos, 26
    );
    expect(historial.map((turno) => turno.content)).toEqual(['dos', 'y'.repeat(10)]);
  });
});

describe('esperaDe', () => {
  /** Una pregunta en marcha, con los pasos y el tiempo que se digan. */
  function enMarcha(pasos: ChatJob['steps'], transcurrido: number): Intercambio {
    return {
      pregunta: '¿Es clickbait?',
      trabajo: {
        id: 'abc',
        status: 'running',
        created_at: '2026-09-28T10:00:00Z',
        steps: pasos,
        result: null,
      },
      error: null,
      enviadaEl: 1_000,
      leidaEl: 1_000 + transcurrido,
    };
  }

  it('sin pasos todavía, está decidiendo qué consultar', () => {
    expect(esperaDe(enMarcha([], 5_000))).toEqual({
      fase: 'Decidiendo qué herramientas usar',
      lleva: '5 s',
      larga: false,
    });
  });

  // El hueco que se leyó como un cuelgue en la aceptación de #191: tras un
  // resultado, 98,8 s sin nada nuevo mientras el modelo razonaba.
  it('tras un resultado, está leyéndolo, y pasado el minuto avisa', () => {
    const espera = esperaDe(
      enMarcha([herramienta('analyze_headline', {})], ESPERA_LARGA_MS + 20_000),
    );
    expect(espera.fase).toContain('Leyendo los resultados');
    expect(espera.lleva).toBe('1 min 20 s');
    expect(espera.larga).toBe(true);
  });

  it('antes de la primera lectura, está enviando', () => {
    const recienEnviada: Intercambio = {
      pregunta: '¿Hola?',
      trabajo: null,
      error: null,
      enviadaEl: 1_000,
      leidaEl: null,
    };
    expect(esperaDe(recienEnviada)).toEqual({
      fase: 'Enviando la pregunta',
      lleva: '0 s',
      larga: false,
    });
  });
});

describe('duracionLegible', () => {
  it('cuenta en segundos y minutos, sin ceros de relleno', () => {
    expect(duracionLegible(12_400)).toBe('12 s');
    expect(duracionLegible(60_000)).toBe('1 min');
    expect(duracionLegible(98_800)).toBe('1 min 38 s');
  });
});

describe('usoHerramientas', () => {
  it('distingue una respuesta apoyada en herramientas de una que no', () => {
    const conHerramienta = terminado('¿Es clickbait?', 'Sí.').trabajo!;
    expect(usoHerramientas(conHerramienta)).toBe(false);
    conHerramienta.steps = [herramienta('detect_clickbait', { label: 'clickbait', score: 1 })];
    expect(usoHerramientas(conHerramienta)).toBe(true);
  });
});
