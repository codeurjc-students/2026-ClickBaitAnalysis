import type { Pista } from './datos';
import { segmentar } from './segmentos';

const TITULAR = "10 Amazing Things You Won't Believe";

const pista = (category: string, cue: string, span: [number, number]): Pista => ({
  category,
  cue,
  span,
});

describe('segmentar', () => {
  it('sin pistas devuelve el titular entero en un tramo', () => {
    expect(segmentar(TITULAR, [])).toEqual([
      { texto: TITULAR, categoria: null },
    ]);
  });

  it('parte el titular en hueco, pista, hueco', () => {
    const segmentos = segmentar(TITULAR, [
      pista('hyperbole', 'Amazing', [3, 10]),
    ]);

    expect(segmentos).toEqual([
      { texto: '10 ', categoria: null },
      { texto: 'Amazing', categoria: 'hyperbole' },
      { texto: " Things You Won't Believe", categoria: null },
    ]);
  });

  it('no deja un tramo vacío cuando la pista empieza en el carácter 0', () => {
    const segmentos = segmentar(TITULAR, [
      pista('leading_number', '10', [0, 2]),
    ]);

    expect(segmentos[0]).toEqual({ texto: '10', categoria: 'leading_number' });
  });

  // Dos categorías sobre el mismo trozo: sin resolverlo saldrían tramos
  // duplicados y el titular se leería dos veces.
  it('ante dos pistas solapadas se queda con la que empieza antes', () => {
    const segmentos = segmentar(TITULAR, [
      pista('hyperbole', 'Amazing', [3, 10]),
      pista('curiosity_gap', 'mazing Things', [4, 17]),
    ]);

    expect(
      segmentos.filter((segmento) => segmento.categoria !== null),
    ).toEqual([{ texto: 'Amazing', categoria: 'hyperbole' }]);
  });

  it('ignora un span fuera de rango sin perder texto', () => {
    const segmentos = segmentar(TITULAR, [
      pista('hyperbole', 'lo que sea', [3, 900]),
    ]);

    expect(segmentos).toEqual([{ texto: TITULAR, categoria: null }]);
  });

  // La invariante que sostiene todo lo demás: los tramos son el titular
  // troceado, así que juntarlos tiene que devolver EXACTAMENTE el original.
  // Ni texto perdido ni repetido.
  it('los tramos recomponen el titular exacto', () => {
    const segmentos = segmentar(TITULAR, [
      pista('leading_number', '10', [0, 2]),
      pista('hyperbole', 'Amazing', [3, 10]),
      pista('forward_reference', 'You', [18, 21]),
    ]);

    expect(segmentos.map((segmento) => segmento.texto).join('')).toBe(TITULAR);
  });
});
