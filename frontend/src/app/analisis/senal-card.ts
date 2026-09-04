import { Component, computed, input, linkedSignal } from '@angular/core';

import type { SignalResult } from '../api/models';
import { comoEtiqueta, comoIncoherencia, comoLexico, comoLineal } from './datos';
import {
  estadoDeSenal,
  nombreDeCategoria,
  nombreDeSenal,
  numero,
} from './vocabulario';

/**
 * Una señal, con el mismo envoltorio sea cual sea y el cuerpo que le
 * corresponda. La parte genérica —nombre, tipo, estado, motivo— no hay que
 * tocarla al añadir una señal; el cuerpo sí, porque explicar ES específico.
 */
@Component({
  selector: 'app-senal-card',
  templateUrl: './senal-card.html',
  styleUrl: './senal-card.scss',
})
export class SenalCard {
  readonly senal = input.required<SignalResult>();

  /**
   * Abierta según el TIPO, no según un número: una señal opaca no tiene
   * explicación que desplegar.
   *
   * `linkedSignal` y no `signal` porque es estado que el usuario puede tocar
   * pero que debe RESEMBRARSE al llegar otra señal. Con un `signal` normal
   * habría que reiniciarlo a mano, y olvidarlo dejaría la tarjeta como la dejó
   * el análisis anterior.
   */
  readonly abierta = linkedSignal(() => this.senal().type !== 'opaque');

  readonly lexico = computed(() => comoLexico(this.senal().data));
  readonly lineal = computed(() => comoLineal(this.senal().data));
  readonly incoherencia = computed(() => comoIncoherencia(this.senal().data));
  readonly etiqueta = computed(() => comoEtiqueta(this.senal().data));
  readonly crudo = computed(() => JSON.stringify(this.senal().data, null, 2));

  /** Las contribuciones no están acotadas: se escalan contra la mayor. */
  private readonly mayorContribucion = computed(() =>
    Math.max(
      0.0001,
      ...(this.lineal()?.top_cues ?? []).map(([, peso]) => Math.abs(peso)),
    ),
  );

  protected readonly nombre = nombreDeSenal;
  protected readonly estado = estadoDeSenal;
  protected readonly categoria = nombreDeCategoria;
  protected readonly numero = numero;

  alternar(): void {
    this.abierta.update((estaAbierta) => !estaAbierta);
  }

  anchoDeCue(peso: number): number {
    return Math.round((Math.abs(peso) / this.mayorContribucion()) * 100);
  }

  porcentaje(valor: number): number {
    return Math.round(Math.min(1, Math.max(0, valor)) * 100);
  }
}
