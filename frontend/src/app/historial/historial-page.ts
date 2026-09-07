import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { SIN_RESPUESTA } from '../api/errores';
import { HistoryService } from '../api/history.service';
import type {
  HistoryEntry,
  HistoryKind,
  HistoryResult,
  OverallVerdict,
  RetentionPolicy,
} from '../api/models';
import { nombreDeVeredicto } from '../analisis/vocabulario';

/** Entradas por página. El contrato admite hasta 100. */
const TAMANO = 20;

/**
 * Los veredictos que ofrece el filtro.
 *
 * Escritos aquí y no derivados de la página cargada: la primera página no
 * contiene necesariamente los cinco, y un filtro que sólo ofrece lo que ya se ve
 * no sirve para buscar. El tipo es la salvaguarda — si el backend renombra uno,
 * esto deja de compilar. Lo que NO caza es que añada un sexto: la lista se
 * quedaría corta en silencio.
 */
const VEREDICTOS: OverallVerdict[] = [
  'deceptive',
  'stylistic_clickbait',
  'factual',
  'ambiguous',
  'no_data',
];

/**
 * Estados de ejecución. Aquí no hay salvaguarda de tipos, y conviene decirlo:
 * `status` es una cadena libre en el contrato, así que estos dos valores salen
 * de leer las llamadas a `history.record()` en `app.py`.
 */
const ESTADOS = ['ok', 'error'];

function mensajeDeFallo(fallo: HttpErrorResponse): string {
  if (fallo.status === 0) return SIN_RESPUESTA;
  if (fallo.status === 422) {
    return 'Los filtros no son válidos. Prueba a limpiarlos.';
  }
  if (fallo.status >= 500) {
    return `La API falló al leer el historial (${fallo.status}).`;
  }
  return `No se pudo cargar el historial (${fallo.status}).`;
}

/**
 * Pantalla de Historial: qué se ha analizado antes, y volver a verlo (R6.5).
 *
 * Lo que hace esta pantalla posible es una decisión del backend: cada entrada
 * guarda la respuesta COMPLETA, no un resumen, así que volver a un análisis no
 * lo reejecuta — y reejecutarlo, además de tardar, podría dar otro resultado,
 * porque las señales remotas no son deterministas.
 */
@Component({
  selector: 'app-historial-page',
  imports: [RouterLink],
  templateUrl: './historial-page.html',
  styleUrl: './historial-page.scss',
})
export class HistorialPage {
  private readonly historial = inject(HistoryService);

  readonly pagina = signal<HistoryResult | null>(null);
  readonly cargando = signal(false);
  readonly error = signal<string | null>(null);

  // Cadena vacía = sin filtrar. Es lo que devuelve un `<select>` en su opción
  // «todas», y el servicio ya sabe que lo vacío no viaja.
  readonly kind = signal<HistoryKind | ''>('');
  readonly verdict = signal('');
  readonly status = signal('');
  readonly offset = signal(0);

  /** Qué ejecución suelta tiene su payload desplegado. */
  readonly abierta = signal<number | null>(null);

  readonly entradas = computed(() => this.pagina()?.items ?? []);
  readonly total = computed(() => this.pagina()?.total ?? 0);

  readonly desde = computed(() => (this.total() === 0 ? 0 : this.offset() + 1));
  readonly hasta = computed(() =>
    Math.min(this.offset() + TAMANO, this.total()),
  );
  readonly hayAnterior = computed(() => this.offset() > 0);
  readonly haySiguiente = computed(() => this.offset() + TAMANO < this.total());

  protected readonly veredictos = VEREDICTOS;
  protected readonly estados = ESTADOS;
  protected readonly veredicto = nombreDeVeredicto;

  constructor() {
    this.cargar();
  }

  cargar(): void {
    if (this.cargando()) return;

    this.cargando.set(true);
    this.error.set(null);

    this.historial
      .pagina({
        limit: TAMANO,
        offset: this.offset(),
        kind: this.kind() || undefined,
        verdict: this.verdict() || undefined,
        status: this.status() || undefined,
      })
      .subscribe({
        next: (pagina) => {
          this.pagina.set(pagina);
          this.cargando.set(false);
        },
        error: (fallo: HttpErrorResponse) => {
          this.error.set(mensajeDeFallo(fallo));
          this.cargando.set(false);
        },
      });
  }

  /**
   * Cambiar un filtro vuelve a la primera página.
   *
   * Sin esto, filtrar desde la página 3 puede dejar la pantalla vacía sobre un
   * resultado que sí tiene entradas — y parece que el filtro no encontró nada.
   */
  filtrar(campo: 'kind' | 'verdict' | 'status', evento: Event): void {
    const valor = (evento.target as HTMLSelectElement).value;

    if (campo === 'kind') this.kind.set(valor as HistoryKind | '');
    if (campo === 'verdict') this.verdict.set(valor);
    if (campo === 'status') this.status.set(valor);

    this.offset.set(0);
    this.abierta.set(null);
    this.cargar();
  }

  pasar(salto: number): void {
    this.offset.update((actual) => Math.max(0, actual + salto * TAMANO));
    this.abierta.set(null);
    this.cargar();
  }

  alternar(id: number): void {
    this.abierta.update((actual) => (actual === id ? null : id));
  }

  /** Fecha local. El backend serializa en UTC con sufijo `Z`, comprobado. */
  fecha(entrada: HistoryEntry): string {
    return new Date(entrada.created_at).toLocaleString('es-ES', {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  }

  crudoDe(entrada: HistoryEntry): string {
    return JSON.stringify(entrada.payload, null, 2);
  }

  /**
   * La retención, en una frase.
   *
   * Se enseña porque **la poda es invisible**: quien analizó algo hace cuarenta
   * días y no lo encuentra no piensa «se habrá podado», piensa que la
   * aplicación perdió sus datos. Y sale de la respuesta, no de constantes de
   * aquí, para que no prometa 30 días el día que cambie el `.env`.
   */
  retencion(politica: RetentionPolicy): string {
    const partes: string[] = [];
    if (politica.max_entries > 0) {
      partes.push(`las últimas ${politica.max_entries.toLocaleString('es-ES')} entradas`);
    }
    if (politica.max_days > 0) partes.push(`los últimos ${politica.max_days} días`);

    if (partes.length === 0) return 'Se conserva todo el historial.';
    return `Se conservan ${partes.join(' y ')}; lo anterior se borra solo.`;
  }
}
