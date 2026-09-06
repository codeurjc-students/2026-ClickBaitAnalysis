/**
 * Formulario de una herramienta, construido desde su esquema (R6.3).
 *
 * No conoce ninguna herramienta: recibe el `input_schema` que publica el
 * catálogo, se lo da a `camposDe` y pinta lo que salga. **Ése es el punto de
 * #128** — añadir una tool al backend no debe tocar el frontend (R1.9).
 *
 * Lo que no se sabe pintar se enseña en crudo en vez de omitirlo, y si además
 * es obligatorio se desactiva el botón: R6.14 dice que la interfaz no debe
 * dejar controles que no funcionen, y un «Ejecutar» que sólo puede producir un
 * 422 es exactamente eso.
 */
import { Component, computed, input, output } from '@angular/core';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
  type AbstractControl,
  type ValidationErrors,
  type ValidatorFn,
} from '@angular/forms';

import type { Argumentos } from '../api/models';
import { camposDe, type Campo } from './campos';

/** Lo que puede valer un control de este formulario. */
type Valor = string | number | boolean | null;

/**
 * Obligatorio, recortando antes de medir: un campo con espacios está vacío para
 * quien lo lee. Es el mismo criterio que el titular de `/analyze`.
 *
 * Escrito aquí y no `Validators.required` por dos razones: aquel da por bueno
 * un campo con espacios, y pasarlo suelto es un método estático sin ligar —lo
 * canta ESLint con tipos (`unbound-method`), y tiene razón: nada garantiza que
 * un día deje de ser independiente de su `this`.
 */
function obligatorio(control: AbstractControl<Valor>): ValidationErrors | null {
  const valor = control.value;
  if (valor === null || valor === '') return { obligatorio: true };
  if (typeof valor === 'string' && !valor.trim()) return { obligatorio: true };
  return null;
}

function validadoresDe(campo: Campo): ValidatorFn[] {
  const validadores: ValidatorFn[] = [];

  // En un booleano `required` significaría «tiene que estar marcado», que no es
  // lo que dice el esquema: dice que la clave tiene que viajar, y un `false`
  // viaja igual.
  if (campo.requerido && campo.tipo !== 'booleano') {
    validadores.push(obligatorio);
  }
  if (campo.minimo !== null) validadores.push(Validators.min(campo.minimo));
  if (campo.maximo !== null) validadores.push(Validators.max(campo.maximo));

  return validadores;
}

/**
 * Valor de arranque: el `default` del esquema si lo hay.
 *
 * Cuando no lo hay, el vacío de cada tipo — y son distintos a propósito: un
 * `null` en una caja de texto pinta la palabra «null».
 */
function inicialDe(campo: Campo): Valor {
  if (campo.valorInicial !== null) return campo.valorInicial;
  if (campo.tipo === 'booleano') return false;
  if (campo.tipo === 'numero') return null;
  return '';
}

@Component({
  selector: 'app-esquema-form',
  imports: [ReactiveFormsModule],
  templateUrl: './esquema-form.html',
})
export class EsquemaForm {
  /** Nombre de la herramienta. Sólo se usa para que los `id` sean únicos: la
   * pantalla monta un formulario por herramienta y los `label` tienen que
   * apuntar al control correcto. */
  readonly herramienta = input.required<string>();

  /**
   * El `input_schema` del catálogo, CRUDO.
   *
   * Entra como `unknown` porque lo publica un servidor MCP que puede no ser el
   * nuestro. Comprobarlo es trabajo de `camposDe`.
   */
  readonly esquema = input.required<unknown>();

  /** Mientras la ejecución está en vuelo, para no lanzar dos. */
  readonly ejecutando = input(false);

  readonly ejecutar = output<Argumentos>();

  readonly campos = computed(() => camposDe(this.esquema()));

  /**
   * El formulario se REHACE cuando cambia el esquema, que es lo que se quiere:
   * son controles distintos, no los mismos con otro valor. Recargar el catálogo
   * borra lo escrito, y es correcto — lo escrito era para otros campos.
   */
  readonly formulario = computed(() => {
    const controles: Record<string, FormControl<Valor>> = {};
    for (const campo of this.campos()) {
      if (campo.tipo === 'desconocido') continue;
      controles[campo.nombre] = new FormControl<Valor>(inicialDe(campo), {
        nonNullable: false,
        validators: validadoresDe(campo),
      });
    }
    return new FormGroup(controles);
  });

  /**
   * Un campo obligatorio que no se sabe pintar impide construir una petición
   * válida: sin él el backend responde 422, y el mensaje hablaría de un campo
   * que el formulario nunca dibujó.
   *
   * Uno OPCIONAL desconocido no bloquea: la herramienta funciona con sus
   * valores por defecto y lo único que se pierde es poder tocar ese parámetro.
   * Se dice en pantalla, que es distinto de esconderlo.
   */
  readonly bloqueado = computed(() =>
    this.campos().some((campo) => campo.tipo === 'desconocido' && campo.requerido),
  );

  idDe(campo: Campo): string {
    return `${this.herramienta()}-${campo.nombre}`;
  }

  /** Ayuda y error van los dos al `aria-describedby`, en ese orden. */
  descritoPor(campo: Campo): string {
    const identificador = this.idDe(campo);
    return campo.descripcion
      ? `ayuda-${identificador} error-${identificador}`
      : `error-${identificador}`;
  }

  crudoDe(campo: Campo): string {
    return JSON.stringify(campo.crudo, null, 2);
  }

  hayError(campo: Campo): boolean {
    const control = this.control(campo);
    return control.touched && control.invalid;
  }

  mensajeDeError(campo: Campo): string {
    const control = this.control(campo);
    if (control.hasError('obligatorio')) {
      return 'Este campo es obligatorio.';
    }
    // Los topes salen del esquema, así que el mensaje dice el número de verdad
    // en vez de uno escrito aquí que podría quedarse viejo.
    if (control.hasError('min')) return `El valor mínimo es ${campo.minimo}.`;
    if (control.hasError('max')) return `El valor máximo es ${campo.maximo}.`;
    return 'El valor no es válido.';
  }

  enviar(): void {
    if (this.ejecutando() || this.bloqueado()) return;

    const formulario = this.formulario();
    if (formulario.invalid) {
      // Sin esto, pulsar Ejecutar con un obligatorio vacío no haría nada
      // visible: los mensajes sólo salen cuando el control se ha tocado.
      formulario.markAllAsTouched();
      return;
    }

    this.ejecutar.emit(this.argumentos());
  }

  /**
   * Los valores que van en la petición.
   *
   * **Lo vacío se OMITE, no se manda como cadena vacía.** No es lo mismo: en
   * `/analyze` mandar `content: ""` es mandar un cuerpo vacío, y omitirlo es no
   * tener cuerpo — con veredictos distintos. Aquí es igual: omitir deja que la
   * herramienta use su valor por defecto.
   *
   * Un booleano nunca está vacío, así que siempre viaja.
   */
  private argumentos(): Argumentos {
    const valores = this.formulario().getRawValue();
    const argumentos: Argumentos = {};

    for (const [nombre, valor] of Object.entries(valores)) {
      if (valor === null || valor === '') continue;
      argumentos[nombre] = valor;
    }

    return argumentos;
  }

  /** El control existe porque el grupo se construye de los mismos campos. */
  private control(campo: Campo): FormControl<Valor> {
    return this.formulario().controls[campo.nombre];
  }
}
