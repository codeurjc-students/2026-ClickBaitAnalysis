import { Component, computed, input } from '@angular/core';

import type { Pista } from './datos';
import { segmentar } from './segmentos';
import { nombreDeCategoria } from './vocabulario';

/**
 * El titular con sus pistas léxicas marcadas.
 *
 * Es R3.8 llevado a la pantalla: la evidencia ES la explicación, así que se
 * enseña sobre el propio texto y no como una lista aparte.
 */
@Component({
  selector: 'app-titular-resaltado',
  templateUrl: './titular-resaltado.html',
  styleUrl: './titular-resaltado.scss',
})
export class TitularResaltado {
  // `input()` da entradas que SON señales: `segmentos` se recalcula solo.
  readonly titular = input.required<string>();
  readonly pistas = input<Pista[]>([]);
  /**
   * El idioma del titular, para su `lang` (#229). Sin valor por defecto: lo
   * decide quien lo pinta, con `idiomaDelTitular`, y un llamador que lo
   * olvidara no compilaría.
   */
  readonly idioma = input.required<string>();

  readonly segmentos = computed(() => segmentar(this.titular(), this.pistas()));

  /** La leyenda sale de lo que apareció, no de una lista fija. */
  readonly categorias = computed(() => [
    ...new Set(
      this.segmentos()
        .map((segmento) => segmento.categoria)
        .filter((categoria): categoria is string => categoria !== null),
    ),
  ]);

  protected readonly nombre = nombreDeCategoria;
}
