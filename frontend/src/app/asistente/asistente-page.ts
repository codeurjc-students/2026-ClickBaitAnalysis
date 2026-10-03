import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  FormBuilder,
  ReactiveFormsModule,
  type AbstractControl,
  type ValidationErrors,
} from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ChatService } from '../api/chat.service';
import { SIN_RESPUESTA, mensajeDeLimite } from '../api/errores';
import type { AgentInfo } from '../api/models';
import { ResultadoAnalisis } from '../senales/resultado-analisis';
import { SenalCard } from '../senales/senal-card';
import {
  CLAVE_GUARDADO,
  aMedias,
  alRecuperar,
  avisoDeGuardado,
  comoIntercambios,
  esperaDe,
  historialQueCabe,
  paraGuardar,
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
 * La conversación se guarda en `sessionStorage` (#209): sobrevive a recargar y
 * a cambiar de sección, dura lo que la pestaña y no sale del navegador. Una
 * pregunta que estaba en marcha se vuelve a seguir. El servidor sigue sin
 * guardar nada entre turnos (decidido al definir H5).
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

  /** Cuántos de los intercambios que se ven están guardados, y si se puede guardar (#209). */
  private readonly guardados = signal(0);
  private readonly almacenamiento = signal(true);
  readonly avisoGuardado = computed(() =>
    avisoDeGuardado(this.intercambios().length, this.guardados(), this.almacenamiento()),
  );

  private readonly campo = viewChild<ElementRef<HTMLTextAreaElement>>('campo');

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
    return !!ultimo && aMedias(ultimo);
  });

  // La plantilla sólo ve miembros de la clase, no imports del módulo.
  protected readonly vista = vistaDePaso;
  protected readonly usoHerramientas = usoHerramientas;
  protected readonly espera = esperaDe;

  constructor() {
    this.comprobar();
    this.recuperar();
    // Cada cambio de la conversación se guarda (#209).
    effect(() => this.guardar(this.intercambios()));
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
      { pregunta, id: null, trabajo: null, error: null, enviadaEl: Date.now(), leidaEl: null },
    ]);
    this.mensaje.reset();

    this.chat
      .preguntar(pregunta, historial)
      .pipe(takeUntilDestroyed(this.destruccion))
      .subscribe({
        next: ({ id }) => {
          // El id se guarda ANTES de la primera lectura: si se sale ahora, con
          // él se puede seguir la pregunta al volver (#209).
          this.actualizar(indice, { id });
          this.seguir(indice, id);
        },
        error: (fallo: HttpErrorResponse) => this.alFallar(indice, fallo),
      });
  }

  /**
   * Vacía la conversación y lo guardado (#209): con la conversación guardada,
   * sería la única forma de empezar otra sin cerrar la pestaña. No con una
   * pregunta en marcha —el servidor seguiría trabajando en algo que ya nadie
   * miraría—, y el foco vuelve al campo de la pregunta.
   */
  empezarDeNuevo(): void {
    if (this.ocupado()) return;
    this.intercambios.set([]);
    this.campo()?.nativeElement.focus();
  }

  /** La condición se usa dos veces: el mensaje y el `aria-invalid`. */
  errorEnMensaje(): boolean {
    return this.mensaje.touched && this.mensaje.invalid;
  }

  /** Sondea una conversación hasta que termina, y va pintando lo que llega. */
  private seguir(indice: number, id: string): void {
    this.chat
      .seguir(id)
      .pipe(takeUntilDestroyed(this.destruccion))
      .subscribe({
        // La hora de cada lectura es la que mueve el «lleva…» de la espera: el
        // sondeo ya lee cada 2 s, así que no hace falta otro temporizador.
        next: (trabajo) => this.actualizar(indice, { trabajo, leidaEl: Date.now() }),
        error: (fallo: HttpErrorResponse) => this.alFallar(indice, fallo),
      });
  }

  private alFallar(indice: number, fallo: HttpErrorResponse): void {
    this.actualizar(indice, { error: mensajeDelChat(fallo) });
    // Un 503 puede ser que la sesión de GPU se cerró mientras tanto: se vuelve
    // a preguntar, y si es así la pantalla lo explica.
    if (fallo.status === 503) this.comprobar();
  }

  /**
   * Lo que dejó guardado la pantalla anterior —al recargar, o al volver a la
   * sección—, y las preguntas que estaban en marcha se vuelven a seguir: el
   * servidor no se enteró de que nadie miraba (#209).
   */
  private recuperar(): void {
    let texto: string | null = null;
    try {
      texto = sessionStorage.getItem(CLAVE_GUARDADO);
    } catch {
      this.almacenamiento.set(false);
    }
    const recuperados = alRecuperar(comoIntercambios(texto));
    this.intercambios.set(recuperados);
    recuperados.forEach((intercambio, indice) => {
      if (aMedias(intercambio) && intercambio.id) this.seguir(indice, intercambio.id);
    });
  }

  /**
   * Guarda la conversación con su tope, y anota cuántos intercambios han cabido
   * para el aviso. Si el navegador no deja —navegación privada, almacenamiento
   * bloqueado o lleno—, la pantalla sigue funcionando y el aviso lo dice.
   */
  private guardar(lista: Intercambio[]): void {
    try {
      if (lista.length === 0) {
        sessionStorage.removeItem(CLAVE_GUARDADO);
        this.guardados.set(0);
      } else {
        const { texto, guardados } = paraGuardar(lista);
        sessionStorage.setItem(CLAVE_GUARDADO, texto);
        this.guardados.set(guardados);
      }
      this.almacenamiento.set(true);
    } catch {
      this.almacenamiento.set(false);
    }
  }

  private actualizar(indice: number, cambios: Partial<Intercambio>): void {
    this.intercambios.update((lista) =>
      lista.map((intercambio, posicion) =>
        posicion === indice ? { ...intercambio, ...cambios } : intercambio,
      ),
    );
  }
}
