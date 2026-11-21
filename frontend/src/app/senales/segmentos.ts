import type { Pista } from './datos';

export interface Segmento {
  texto: string;
  categoria: string | null; // null = trozo sin resaltar
}

/**
 * Trocea el titular en tramos resaltados y sin resaltar.
 *
 * Los `span` PUEDEN SOLAPARSE: un mismo trozo dispara más de una categoría.
 * Regla: gana la que empieza antes, y a igualdad la más larga. Es arbitraria,
 * pero determinista — sin ella saldrían tramos duplicados.
 *
 * Los `span` cuentan PUNTOS DE CÓDIGO, como Python, y aquí se trocea igual.
 * `String.length` y `slice` cuentan unidades UTF-16, en las que un emoji ocupa
 * dos: hasta la revisión de antes de congelar, cada emoji anterior a una pista
 * corría la marca un carácter, y podía partirlo por la mitad.
 */
export function segmentar(titular: string, pistas: Pista[]): Segmento[] {
  const caracteres = Array.from(titular);
  const tramo = (desde: number, hasta?: number) =>
    caracteres.slice(desde, hasta).join('');

  const ordenadas = [...pistas]
    // Defensivo: un span fuera de rango produciría recortes raros y texto
    // perdido. Se ignora esa pista y el titular se pinta entero igualmente.
    .filter(
      (pista) =>
        pista.span[0] >= 0 &&
        pista.span[1] <= caracteres.length &&
        pista.span[0] < pista.span[1],
    )
    .sort(
      (una, otra) => una.span[0] - otra.span[0] || otra.span[1] - una.span[1],
    );

  const segmentos: Segmento[] = [];
  let cursor = 0;

  for (const pista of ordenadas) {
    const [inicio, fin] = pista.span;
    if (inicio < cursor) continue; // solapa con una anterior
    if (inicio > cursor) {
      segmentos.push({ texto: tramo(cursor, inicio), categoria: null });
    }
    segmentos.push({ texto: tramo(inicio, fin), categoria: pista.category });
    cursor = fin;
  }

  if (cursor < caracteres.length) {
    segmentos.push({ texto: tramo(cursor), categoria: null });
  }
  return segmentos;
}
