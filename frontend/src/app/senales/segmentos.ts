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
 */
export function segmentar(titular: string, pistas: Pista[]): Segmento[] {
  const ordenadas = [...pistas]
    // Defensivo: un span fuera de rango produciría recortes raros y texto
    // perdido. Se ignora esa pista y el titular se pinta entero igualmente.
    .filter(
      (pista) =>
        pista.span[0] >= 0 &&
        pista.span[1] <= titular.length &&
        pista.span[0] < pista.span[1],
    )
    .sort((a, b) => a.span[0] - b.span[0] || b.span[1] - a.span[1]);

  const segmentos: Segmento[] = [];
  let cursor = 0;

  for (const pista of ordenadas) {
    const [inicio, fin] = pista.span;
    if (inicio < cursor) continue; // solapa con una anterior
    if (inicio > cursor) {
      segmentos.push({ texto: titular.slice(cursor, inicio), categoria: null });
    }
    segmentos.push({ texto: titular.slice(inicio, fin), categoria: pista.category });
    cursor = fin;
  }

  if (cursor < titular.length) {
    segmentos.push({ texto: titular.slice(cursor), categoria: null });
  }
  return segmentos;
}
