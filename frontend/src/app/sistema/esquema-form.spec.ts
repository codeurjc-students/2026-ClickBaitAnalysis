import { TestBed, type ComponentFixture } from '@angular/core/testing';

import type { Argumentos } from '../api/models';
import { EsquemaForm } from './esquema-form';

/**
 * Los esquemas son los que publican las tools de verdad. Uno inventado probaría
 * que el formulario funciona con lo que yo imagino.
 */
const CLICKBAIT = {
  type: 'object',
  properties: { headline: { type: 'string', title: 'Headline' } },
  required: ['headline'],
};

const NOTICIAS = {
  type: 'object',
  properties: {
    topic: {
      anyOf: [{ type: 'string' }, { type: 'null' }],
      default: null,
      description: 'Tema a buscar.',
    },
    days: { type: 'integer', minimum: 1, maximum: 30, default: 7 },
  },
};

const SIN_PARAMETROS = { type: 'object', properties: {} };

const CON_ARRAY = {
  type: 'object',
  properties: { etiquetas: { type: 'array', items: { type: 'string' } } },
  required: ['etiquetas'],
};

describe('EsquemaForm', () => {
  let fixture: ComponentFixture<EsquemaForm>;
  let enviados: Argumentos[];

  const montar = async (herramienta: string, esquema: unknown) => {
    fixture = TestBed.createComponent(EsquemaForm);
    fixture.componentRef.setInput('herramienta', herramienta);
    fixture.componentRef.setInput('esquema', esquema);

    enviados = [];
    fixture.componentInstance.ejecutar.subscribe((argumentos) => {
      enviados.push(argumentos);
    });

    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  };

  const ejecutar = async (raiz: HTMLElement) => {
    raiz.querySelector<HTMLButtonElement>('button[type="submit"]')?.click();
    await fixture.whenStable();
  };

  // Lo que hace que añadir una tool no toque esto: nadie escribió «headline».
  it('pinta los campos que declara el esquema', async () => {
    const raiz = await montar('detect_clickbait', CLICKBAIT);

    const etiqueta = raiz.querySelector('label');
    expect(etiqueta?.textContent).toContain('headline');
    expect(etiqueta?.getAttribute('for')).toBe('campo-detect_clickbait-headline');
  });

  it('arranca con el valor por defecto del esquema', async () => {
    const raiz = await montar('get_nyt_news', NOTICIAS);

    const dias = raiz.querySelector<HTMLInputElement>('#campo-get_nyt_news-days');
    expect(dias?.value).toBe('7');
    // Los topes también viajan al control, no sólo al validador.
    expect(dias?.getAttribute('min')).toBe('1');
    expect(dias?.getAttribute('max')).toBe('30');
  });

  // Omitir y mandar vacío NO es lo mismo: omitir deja que la herramienta use su
  // valor por defecto, y `""` es una búsqueda de la cadena vacía.
  it('no manda los opcionales que quedan en blanco', async () => {
    const raiz = await montar('get_nyt_news', NOTICIAS);

    await ejecutar(raiz);

    expect(enviados).toEqual([{ days: 7 }]);
  });

  it('manda el opcional cuando se rellena', async () => {
    const raiz = await montar('get_nyt_news', NOTICIAS);

    fixture.componentInstance.formulario().controls['topic'].setValue('clima');
    await ejecutar(raiz);

    expect(enviados).toEqual([{ topic: 'clima', days: 7 }]);
  });

  it('con el obligatorio en blanco no ejecuta, y lo dice', async () => {
    const raiz = await montar('detect_clickbait', CLICKBAIT);

    await ejecutar(raiz);

    expect(enviados).toEqual([]);
    expect(raiz.textContent).toContain('Este campo es obligatorio');
    const control = raiz.querySelector('#campo-detect_clickbait-headline');
    expect(control?.getAttribute('aria-invalid')).toBe('true');
  });

  // El mensaje dice el número del esquema, no uno escrito en la plantilla que
  // se quedaría viejo al cambiar la tool.
  it('respeta el tope que declara el esquema', async () => {
    const raiz = await montar('get_nyt_news', NOTICIAS);

    fixture.componentInstance.formulario().controls['days'].setValue(99);
    await ejecutar(raiz);

    expect(enviados).toEqual([]);
    expect(raiz.textContent).toContain('El valor máximo es 30.');
  });

  it('una herramienta sin parámetros ejecuta con el cuerpo vacío', async () => {
    const raiz = await montar('describe_models', SIN_PARAMETROS);

    expect(raiz.textContent).toContain('no necesita parámetros');
    await ejecutar(raiz);

    expect(enviados).toEqual([{}]);
  });

  // R6.14: nada de controles que sólo pueden producir un 422. Y el esquema a la
  // vista, que es lo único que explica por qué no se puede.
  it('un obligatorio que no se sabe pintar desactiva Ejecutar', async () => {
    const raiz = await montar('tool_futura', CON_ARRAY);

    const boton = raiz.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(boton?.disabled).toBe(true);
    expect(raiz.textContent).toContain('etiquetas');
    expect(raiz.querySelector('pre')?.textContent).toContain('"type": "array"');
  });

  it('un opcional que no se sabe pintar se enseña, pero deja ejecutar', async () => {
    const raiz = await montar('tool_futura', {
      ...CON_ARRAY,
      required: [],
    });

    const boton = raiz.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(boton?.disabled).toBe(false);
    expect(raiz.textContent).toContain('usará su valor por defecto');

    await ejecutar(raiz);
    expect(enviados).toEqual([{}]);
  });
});
