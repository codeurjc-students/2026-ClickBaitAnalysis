import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import {
  FormBuilder,
  ReactiveFormsModule,
  type AbstractControl,
  type ValidationErrors,
} from '@angular/forms';

import { Router } from '@angular/router';

import { AnalyzeService } from '../api/analyze.service';
import { HistoryService } from '../api/history.service';
import { comoAnalisis, type AnalisisGuardado } from './formas';
import { comoLexico, type Pista } from './datos';
import { mensajeDeError } from './errores';
import { SenalCard } from './senal-card';
import { TitularResaltado } from './titular-resaltado';
import {
  estadoDeSenal,
  nombreDeDimension,
  nombreDeSenal,
  nombreDeVeredicto,
  resumenDimension,
} from './vocabulario';

/** Espeja `NonBlankStr` del backend: recorta antes de medir. */
function noEnBlanco(control: AbstractControl<string>): ValidationErrors | null {
  return control.value.trim() ? null : { enBlanco: true };
}

@Component({
  selector: 'app-analisis-page',
  imports: [ReactiveFormsModule, TitularResaltado, SenalCard],
  templateUrl: './analisis-page.html',
  styleUrl: './analisis-page.scss',
})
export class AnalisisPage {
  private readonly analyze = inject(AnalyzeService);
  private readonly historial = inject(HistoryService);
  private readonly router = inject(Router);

  readonly formulario = inject(FormBuilder).nonNullable.group({
    headline: ['', noEnBlanco],
    content: [''],
  });

  // En zoneless el estado VA en señales: en campos normales la vista no se
  // repintaría, y no saltaría ningún error.
  readonly enviando = signal(false);
  readonly error = signal<string | null>(null);
  readonly resultado = signal<AnalisisGuardado | null>(null);

  /**
   * Id de la entrada del historial en la que quedó este análisis (#133).
   *
   * Va en una señal aparte y no dentro de `resultado` para que la plantilla
   * siga viendo el análisis directamente. Puede ser `null` —el registro falla y
   * el análisis sigue siendo válido—, así que nada puede depender de él.
   *
   * Hoy no se pinta: existe para que la futura ruta `/analisis/:id` sea
   * aditiva, que es como #127 dejó preparado este componente.
   */
  readonly idAnalisis = signal<number | null>(null);

  /**
   * Id de la entrada que se está viendo, cuando se llega por `/analisis/:id`.
   *
   * Llega del ROUTER y no de un padre: lo enlaza `withComponentInputBinding()`
   * en `app.config.ts`. Sin id, la pantalla es el formulario de siempre.
   */
  readonly id = input<string>();

  /** Cuándo se guardó lo que se está viendo. `null` si es de ahora mismo. */
  readonly guardadoEl = signal<string | null>(null);

  readonly fechaGuardado = computed(() => {
    const cuando = this.guardadoEl();
    if (!cuando) return null;
    // El backend serializa en UTC con sufijo `Z`, comprobado contra la
    // base local: sin la Z, `new Date` lo leería como hora local.
    return new Date(cuando).toLocaleString('es-ES', {
      dateStyle: 'long',
      timeStyle: 'short',
    });
  });

  readonly veredicto = computed(() => {
    const analisis = this.resultado();
    return analisis ? nombreDeVeredicto(analisis.verdict) : null;
  });

  // La plantilla sólo ve miembros de la clase, no imports del módulo.
  protected readonly nombre = nombreDeSenal;
  protected readonly estado = estadoDeSenal;
  protected readonly dimension = nombreDeDimension;
  protected readonly resumen = resumenDimension;

  constructor() {
    // Un `effect` y no una carga en el constructor porque el id puede CAMBIAR
    // sin que el componente se destruya: navegar de /analisis/28 a /analisis/29
    // reutiliza esta instancia, y el constructor no se ejecuta otra vez.
    effect(() => {
      const identificador = this.id();
      if (identificador) this.recuperar(Number(identificador));
    });
  }

  /**
   * Recupera un análisis guardado en vez de reejecutarlo.
   *
   * El payload se COMPRUEBA, no se castea: el historial guarda respuestas de
   * versiones anteriores del contrato. Si no encaja, se dice — y el JSON crudo
   * sigue estando a mano en la pantalla del historial.
   */
  private recuperar(id: number): void {
    this.enviando.set(true);
    this.error.set(null);

    this.historial.entrada(id).subscribe({
      next: (entrada) => {
        const analisis = comoAnalisis(entrada.payload);

        if (analisis) {
          this.resultado.set(analisis);
          this.idAnalisis.set(entrada.id);
          this.guardadoEl.set(entrada.created_at);
        } else {
          this.error.set(
            'Esa entrada no tiene forma de análisis. Se puede ver en crudo desde el historial.',
          );
        }
        this.enviando.set(false);
      },
      error: (fallo: HttpErrorResponse) => {
        // El 404 tiene mensaje propio porque aquí NO es una rareza: la
        // retención borra las entradas viejas, así que un enlace guardado deja
        // de existir por funcionamiento normal. Decir "no se pudo cargar"
        // sonaría a avería.
        this.error.set(
          fallo.status === 404
            ? 'Ese análisis ya no está en el historial: la retención borra las entradas más viejas.'
            : mensajeDeError(fallo),
        );
        this.enviando.set(false);
      },
    });
  }

  analizar(): void {
    // Dos envíos son dos ejecuciones de los modelos y dos entradas de historial.
    if (this.enviando()) return;
    if (this.formulario.invalid) {
      // Sin esto, pulsar Analizar con el campo vacío no haría nada visible.
      this.formulario.controls.headline.markAsTouched();
      return;
    }

    const { headline, content } = this.formulario.getRawValue();
    this.enviando.set(true);
    this.error.set(null);

    this.analyze
      // Sin cuerpo se omite la clave entera, que es lo que deja la incoherencia
      // en `not_applicable`. Mandar "" sería otra cosa: un cuerpo vacío.
      .analizar({
        headline: headline.trim(),
        content: content.trim() || undefined,
      })
      .subscribe({
        next: (respuesta) => {
          // El sobre se abre AQUÍ y sólo aquí: es el precio de llevar el id al
          // lado del análisis, y se paga una vez.
          this.resultado.set(respuesta.analysis);
          this.idAnalisis.set(respuesta.id ?? null);
          this.enviando.set(false);
        },
        error: (fallo: HttpErrorResponse) => {
          this.error.set(mensajeDeError(fallo));
          this.enviando.set(false);
        },
      });
  }

  nuevoAnalisis(): void {
    // Viendo algo guardado, volver al formulario es CAMBIAR DE RUTA: limpiar
    // las señales dejaría la URL diciendo /analisis/29 sobre una pantalla
    // vacía, y recargar traería de vuelta el análisis viejo.
    if (this.guardadoEl()) {
      void this.router.navigate(['/analizar']);
      return;
    }

    this.guardadoEl.set(null);
    this.resultado.set(null);
    this.idAnalisis.set(null);
    this.error.set(null);
    this.formulario.reset();
  }

  ejemplo(titular: string): void {
    this.formulario.controls.headline.setValue(titular);
  }

  /**
   * Las pistas léxicas con las que se resalta el titular.
   *
   * Vacío si la señal falló o si su `data` no tiene la forma esperada: el
   * titular se pinta entero y sin marcas, que es degradar, no romperse.
   */
  pistasDe(analisis: AnalisisGuardado): Pista[] {
    const lexica = analisis.signals.find(
      (senal) => senal.name === 'detect_clickbait_lexical',
    );
    return comoLexico(lexica?.data)?.matches ?? [];
  }

  /** La condición se usa dos veces: el mensaje y el `aria-invalid`. */
  errorEnTitular(): boolean {
    const control = this.formulario.controls.headline;
    return control.touched && control.invalid;
  }
}
