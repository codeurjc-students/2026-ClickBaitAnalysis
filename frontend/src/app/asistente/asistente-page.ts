import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  FormBuilder,
  ReactiveFormsModule,
  type AbstractControl,
  type ValidationErrors,
} from '@angular/forms';
import { RouterLink } from '@angular/router';
import { switchMap } from 'rxjs';

import { ChatService } from '../api/chat.service';
import { SIN_RESPUESTA, mensajeDeLimite } from '../api/errores';
import type { AgentInfo, ChatJob } from '../api/models';
import { ResultadoAnalisis } from '../senales/resultado-analisis';
import { SenalCard } from '../senales/senal-card';
import {
  historialQueCabe,
  usoHerramientas,
  vistaDePaso,
  type Intercambio,
} from './conversacion';
import { mensajeDelChat } from './errores';

/** Espeja la validación del backend: recorta antes de mirar si hay algo. */
function noEnBlanco(control: AbstractControl<string>): ValidationErrors | null {
  return control.value.trim() ? null : { enBlanco: true };
}

/**
 * La pantalla del asistente conversacional (R13, R6.10–R6.14, #191).
 *
 * **Sin asistente, se explica por qué** (R6.14): distinguiendo «no está
 * configurado en este despliegue» de «está apagado, se arranca bajo demanda»,
 * y sin campo de texto ni botón que no puedan funcionar.
 *
 * **Con asistente**, cada pregunta se manda con el texto de los intercambios
 * anteriores —el servidor no guarda nada entre turnos— y su conversación se
 * sondea hasta que termina. La traza se pinta según crece: cada herramienta
 * con su resultado, que es de donde sale el veredicto (R13.4), y la narración
 * del modelo al final. Si la narración llega vacía, las tarjetas se ven igual
 * (R6.13).
 *
 * El historial de la pantalla vive en memoria del componente: salir de la ruta
 * lo pierde, igual que el servidor no lo guarda (decidido al definir H5).
 */
@Component({
  selector: 'app-asistente-page',
  imports: [ReactiveFormsModule, RouterLink, ResultadoAnalisis, SenalCard],
  templateUrl: './asistente-page.html',
  styleUrl: './asistente-page.scss',
})
export class AsistentePage {
  private readonly chat = inject(ChatService);
  private readonly destruccion = inject(DestroyRef);

  // En zoneless el estado VA en señales: en campos normales la vista no se
  // repintaría, y no saltaría ningún error.
  readonly agente = signal<AgentInfo | null>(null);
  readonly comprobando = signal(true);
  readonly errorAgente = signal<string | null>(null);
  readonly intercambios = signal<Intercambio[]>([]);

  // Un grupo aunque tenga un solo campo: sin `formGroup` en el `<form>`,
  // `ngSubmit` no se dispara, y el navegador haría el envío nativo, que
  // recarga la página. Lo cazó el spec antes de verse en producción.
  readonly formulario = inject(FormBuilder).nonNullable.group({
    mensaje: ['', noEnBlanco],
  });
  readonly mensaje = this.formulario.controls.mensaje;

  readonly disponible = computed(
    () => this.agente()?.availability.status === 'available',
  );

  /**
   * Hay una pregunta en marcha. Mientras tanto no se manda otra: la siguiente
   * tiene que llevar esta respuesta en su historial, y la GPU atiende una
   * conversación cada vez de todas formas (#189).
   */
  readonly ocupado = computed(() => {
    const ultimo = this.intercambios().at(-1);
    return !!ultimo && !ultimo.error && ultimo.trabajo?.status !== 'done';
  });

  // La plantilla sólo ve miembros de la clase, no imports del módulo.
  protected readonly vista = vistaDePaso;
  protected readonly usoHerramientas = usoHerramientas;

  constructor() {
    this.comprobar();
  }

  /** Pregunta si el asistente se puede usar ahora. */
  comprobar(): void {
    this.comprobando.set(true);
    this.errorAgente.set(null);
    this.chat
      .agente()
      .pipe(takeUntilDestroyed(this.destruccion))
      .subscribe({
        next: (informacion) => {
          this.agente.set(informacion);
          this.comprobando.set(false);
        },
        error: (fallo: HttpErrorResponse) => {
          this.errorAgente.set(
            fallo.status === 0
              ? SIN_RESPUESTA
              : fallo.status === 429
                ? mensajeDeLimite(fallo)
                : `No se pudo saber si el asistente está disponible (${fallo.status}).`,
          );
          this.comprobando.set(false);
        },
      });
  }

  enviar(): void {
    const informacion = this.agente();
    if (this.ocupado() || !informacion || !this.disponible()) return;
    if (this.mensaje.invalid) {
      // Sin esto, enviar con el campo vacío no haría nada visible.
      this.mensaje.markAsTouched();
      return;
    }

    const pregunta = this.mensaje.value.trim();
    const historial = historialQueCabe(
      this.intercambios(),
      informacion.max_history_chars,
    );
    const indice = this.intercambios().length;
    this.intercambios.update((lista) => [
      ...lista,
      { pregunta, trabajo: null, error: null },
    ]);
    this.mensaje.reset();

    this.chat
      .preguntar(pregunta, historial)
      .pipe(
        switchMap(({ id }) => this.chat.seguir(id)),
        takeUntilDestroyed(this.destruccion),
      )
      .subscribe({
        next: (trabajo) => this.actualizar(indice, { trabajo }),
        error: (fallo: HttpErrorResponse) => {
          this.actualizar(indice, { error: mensajeDelChat(fallo) });
          // Un 503 puede ser que la sesión de GPU se cerró mientras tanto: se
          // vuelve a preguntar, y si es así la pantalla lo explica.
          if (fallo.status === 503) this.comprobar();
        },
      });
  }

  /** La condición se usa dos veces: el mensaje y el `aria-invalid`. */
  errorEnMensaje(): boolean {
    return this.mensaje.touched && this.mensaje.invalid;
  }

  herramientasDe(trabajo: ChatJob): number {
    return trabajo.steps.filter((paso) => paso.kind === 'tool').length;
  }

  private actualizar(indice: number, cambios: Partial<Intercambio>): void {
    this.intercambios.update((lista) =>
      lista.map((intercambio, posicion) =>
        posicion === indice ? { ...intercambio, ...cambios } : intercambio,
      ),
    );
  }
}
