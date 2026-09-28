import { Component, computed, input } from '@angular/core';

import { comoLexico, type Pista } from './datos';
import type { AnalisisGuardado } from './formas';
import { SenalCard } from './senal-card';
import { TitularResaltado } from './titular-resaltado';
import {
  estadoDeSenal,
  funciono,
  nombreCortoDeSenal,
  nombreDeDimension,
  nombreDeVeredicto,
  resumenDimension,
} from './vocabulario';

/**
 * Un análisis completo: el veredicto, el titular con sus pistas, cada dimensión,
 * el índice de señales y una tarjeta por señal.
 *
 * Vivía dentro de la plantilla de la pantalla de análisis, y salió de ahí en
 * #191 porque el asistente pinta lo mismo cuando el agente llama a
 * `analyze_headline`. Recibe el análisis ya comprobado (`comoAnalisis`), así
 * que le da igual de dónde venga: del formulario, del historial o de la traza
 * de una conversación.
 */
@Component({
  selector: 'app-resultado-analisis',
  imports: [SenalCard, TitularResaltado],
  templateUrl: './resultado-analisis.html',
  styleUrl: './resultado-analisis.scss',
})
export class ResultadoAnalisis {
  readonly analisis = input.required<AnalisisGuardado>();

  readonly veredicto = computed(() => nombreDeVeredicto(this.analisis().verdict));

  /**
   * Las pistas léxicas con las que se resalta el titular.
   *
   * Vacío si la señal falló o si su `data` no tiene la forma esperada: el
   * titular se pinta entero y sin marcas, que es degradar, no romperse.
   */
  readonly pistas = computed<Pista[]>(() => {
    const lexica = this.analisis().signals.find(
      (senal) => senal.name === 'detect_clickbait_lexical',
    );
    return comoLexico(lexica?.data)?.matches ?? [];
  });

  // La plantilla sólo ve miembros de la clase, no imports del módulo.
  protected readonly nombreCorto = nombreCortoDeSenal;
  protected readonly estado = estadoDeSenal;
  protected readonly funciono = funciono;
  protected readonly dimension = nombreDeDimension;
  protected readonly resumen = resumenDimension;
}
