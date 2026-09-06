import { camposDe } from './campos';

/**
 * Los esquemas de aquí son los REALES, copiados de lo que publican las tools
 * (comprobado contra `mcp.list_tools()` al planificar #128). Inventarlos
 * probaría que el lector funciona con lo que yo imagino, no con lo que llega.
 */

describe('camposDe', () => {
  it('lee un campo de texto obligatorio', () => {
    const [campo] = camposDe({
      type: 'object',
      properties: { headline: { type: 'string', title: 'Headline' } },
      required: ['headline'],
    });

    expect(campo.nombre).toBe('headline');
    expect(campo.tipo).toBe('texto');
    expect(campo.requerido).toBe(true);
  });

  it('resuelve el opcional que FastAPI publica como anyOf con null', () => {
    // `topic: str | None = None` en Python NO llega como `type: "string"`. Sin
    // resolver este caso, los tres campos opcionales del catálogo saldrían como
    // desconocidos y la pantalla los pintaría en crudo sin motivo.
    const [campo] = camposDe({
      type: 'object',
      properties: {
        topic: {
          anyOf: [{ type: 'string' }, { type: 'null' }],
          default: null,
          description: 'Tema a buscar.',
        },
      },
    });

    expect(campo.tipo).toBe('texto');
    expect(campo.requerido).toBe(false);
    expect(campo.descripcion).toBe('Tema a buscar.');
  });

  it('conserva los topes y el valor por defecto de un entero', () => {
    // Es la razón de que el catálogo publique el esquema CRUDO en vez de
    // aplanarlo: sin esto la interfaz no puede validar antes de enviar.
    const [campo] = camposDe({
      type: 'object',
      properties: {
        days: { type: 'integer', minimum: 1, maximum: 30, default: 7 },
      },
    });

    expect(campo.tipo).toBe('numero');
    expect(campo.minimo).toBe(1);
    expect(campo.maximo).toBe(30);
    expect(campo.valorInicial).toBe(7);
  });

  it('una herramienta sin parámetros no tiene campos', () => {
    // `describe_models` y `health_check` son así: sólo un botón.
    expect(camposDe({ type: 'object', properties: {} })).toEqual([]);
  });

  it('marca como desconocido lo que no sabe pintar, y guarda el fragmento', () => {
    // Omitirlo mandaría un cuerpo incompleto y el 422 llegaría sin explicación.
    // Enseñarlo en crudo es feo y dice la verdad.
    const [campo] = camposDe({
      type: 'object',
      properties: { etiquetas: { type: 'array', items: { type: 'string' } } },
      required: ['etiquetas'],
    });

    expect(campo.tipo).toBe('desconocido');
    expect(campo.requerido).toBe(true);
    expect(campo.crudo).toEqual({ type: 'array', items: { type: 'string' } });
  });

  it('una unión de verdad tampoco se sabe pintar', () => {
    // El `anyOf` sólo se resuelve cuando queda UN tipo al quitar el null.
    const [campo] = camposDe({
      type: 'object',
      properties: { valor: { anyOf: [{ type: 'string' }, { type: 'integer' }] } },
    });

    expect(campo.tipo).toBe('desconocido');
  });

  it('no revienta con un esquema que no tiene la forma esperada', () => {
    // Llega de un servidor MCP ajeno: puede ser cualquier cosa.
    expect(camposDe(null)).toEqual([]);
    expect(camposDe({ type: 'object' })).toEqual([]);
    expect(camposDe('no soy un esquema')).toEqual([]);
  });
});
