import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';

import { detalleDeValidacion, SIN_RESPUESTA } from '../api/errores';
import type { Argumentos, CatalogResult, ExecuteResult } from '../api/models';
import { ToolsService } from '../api/tools.service';
import { nombreDeDimension } from '../analisis/vocabulario';
import { EsquemaForm } from './esquema-form';

/** El catálogo no se pudo construir. */
function mensajeDeCatalogo(fallo: HttpErrorResponse): string {
  if (fallo.status === 0) return SIN_RESPUESTA;
  if (fallo.status >= 500) {
    return `La API falló al construir el catálogo (${fallo.status}).`;
  }
  return `No se pudo cargar el catálogo (${fallo.status}).`;
}

/**
 * La ejecución no llegó a producir un resultado.
 *
 * Los tres casos se separan porque el remedio es distinto en cada uno, y
 * fundirlos en «no se pudo ejecutar» los volvería inaccionables. El 504 es el
 * que más importa: **no dice que la herramienta fallara**, dice que se agotó la
 * espera — en #113 terminó bien a los 151 s con la API ya desistida.
 */
function mensajeDeEjecucion(fallo: HttpErrorResponse): string {
  if (fallo.status === 0) return SIN_RESPUESTA;
  if (fallo.status === 404) {
    return 'Esa herramienta ya no está en el catálogo. Recarga la lista.';
  }
  if (fallo.status === 422) {
    const detalle = detalleDeValidacion(fallo.error);
    return detalle
      ? `Los argumentos no encajan en el esquema: ${detalle}`
      : 'Los argumentos no encajan en el esquema de la herramienta.';
  }
  if (fallo.status === 504) {
    return 'Se agotó la espera. La herramienta puede haber terminado igualmente, así que repetir la llamada la ejecutaría otra vez.';
  }
  if (fallo.status >= 500) return `La API falló al ejecutar (${fallo.status}).`;
  return `No se pudo ejecutar la herramienta (${fallo.status}).`;
}

/**
 * Deja un texto listo para comparar en el buscador.
 *
 * Se aplica igual a lo escrito y a lo buscado, así que lo que decida esta
 * función ES lo que la búsqueda considera «igual». Por eso quitar diacríticos
 * sólo puede SUMAR coincidencias: lo que encajaba antes sigue encajando.
 */
function normalizar(texto: string): string {
  // Caen todos los diacríticos, la ñ INCLUIDA, y es a propósito: medido sobre
  // las docstrings del catálogo, ninguna palabra colisiona con otra al
  // perderlos (`señal`, `engaño`, `añadir`, `pestañas`). No es un descuido que
  // haya que arreglar.
  return texto
    .trim()
    .normalize('NFD')
    .toLowerCase()
    .replace(/\p{Diacritic}/gu, '');
}

/**
 * Pantalla de Sistema: qué hay conectado, qué ofrece y con qué modelos.
 *
 * Tres secciones que responden tres preguntas distintas — servidores (R6.11),
 * catálogo con búsqueda y filtro (R6.2, R6.9) y fichas de modelo (R3.8)— y una
 * cuarta cosa que NO está aquí: la salud de las APIs externas, que sale de
 * `/health` y es otra pregunta (issue #147).
 *
 * **No es un lanzador.** Se puede ejecutar una herramienta suelta porque hace
 * falta para probar una señal sin pasar por el análisis completo, pero el
 * camino normal del producto es `/analizar`.
 */
@Component({
  selector: 'app-sistema-page',
  imports: [EsquemaForm],
  templateUrl: './sistema-page.html',
  styleUrl: './sistema-page.scss',
})
export class SistemaPage {
  private readonly tools = inject(ToolsService);

  readonly catalogo = signal<CatalogResult | null>(null);
  readonly cargando = signal(false);
  readonly error = signal<string | null>(null);

  readonly busqueda = signal('');
  readonly categoria = signal('');

  /**
   * Qué herramienta tiene el formulario desplegado. Una sola: con doce tools,
   * todas abiertas serían doce formularios y ninguna vista de conjunto.
   */
  readonly abierta = signal<string | null>(null);

  /**
   * Qué herramienta se está ejecutando, o `null`. Una a la vez a propósito: en
   * la máquina de despliegue no hay GPU, y dos señales pesadas en paralelo se
   * estorban.
   */
  readonly ejecutando = signal<string | null>(null);

  // Por nombre de herramienta, para que el resultado se quede donde se pidió al
  // desplegar otra.
  readonly resultados = signal<Record<string, ExecuteResult>>({});
  readonly fallos = signal<Record<string, string>>({});

  readonly servidores = computed(() => this.catalogo()?.servers ?? []);
  readonly herramientas = computed(() => this.catalogo()?.tools ?? []);

  /**
   * Las categorías salen del catálogo, no de una lista escrita aquí.
   *
   * Es la misma razón que el formulario generado: el backend las declara en
   * `integrations/metadata.py`, y si aparece una quinta el filtro la ofrece sin
   * tocar el frontend (R1.9).
   */
  readonly categorias = computed(() => {
    const vistas = new Set<string>();
    for (const herramienta of this.herramientas()) {
      if (herramienta.category) vistas.add(herramienta.category);
    }
    return [...vistas].sort((primera, segunda) => primera.localeCompare(segunda, 'es'));
  });

  /** Filtrado en cliente: son doce herramientas, no hace falta volver a pedir. */
  readonly filtradas = computed(() => {
    const texto = normalizar(this.busqueda());
    const categoria = this.categoria();

    return this.herramientas().filter((herramienta) => {
      if (categoria && herramienta.category !== categoria) return false;
      if (!texto) return true;
      return (
        normalizar(herramienta.name).includes(texto) ||
        normalizar(herramienta.description ?? '').includes(texto)
      );
    });
  });

  /** Las que llevan ficha son exactamente las señales de análisis. */
  readonly fichas = computed(() =>
    this.herramientas().filter((herramienta) => herramienta.model_card),
  );

  protected readonly dimension = nombreDeDimension;

  constructor() {
    this.cargar();
  }

  /**
   * Pide el catálogo. Se llama al montar y desde el botón de recargar, nunca en
   * bucle: cada llamada es un handshake contra cada servidor MCP.
   */
  cargar(): void {
    if (this.cargando()) return;

    this.cargando.set(true);
    this.error.set(null);

    this.tools.catalogo().subscribe({
      next: (catalogo) => {
        this.catalogo.set(catalogo);
        this.cargando.set(false);
      },
      error: (fallo: HttpErrorResponse) => {
        this.error.set(mensajeDeCatalogo(fallo));
        this.cargando.set(false);
      },
    });
  }

  alternar(nombre: string): void {
    this.abierta.update((actual) => (actual === nombre ? null : nombre));
  }

  buscar(evento: Event): void {
    this.busqueda.set((evento.target as HTMLInputElement).value);
  }

  filtrarPorCategoria(evento: Event): void {
    this.categoria.set((evento.target as HTMLSelectElement).value);
  }

  /**
   * Ejecuta la herramienta y guarda lo que conteste.
   *
   * **Un `status: 'error'` llega por `next`**, no por el canal de error: la
   * petición era válida y el servidor la atendió, lo que falló es la
   * herramienta. Se guarda igual que un resultado bueno, porque su `detail` es
   * lo único que explica qué pasó.
   */
  ejecutarHerramienta(nombre: string, argumentos: Argumentos): void {
    if (this.ejecutando()) return;

    this.ejecutando.set(nombre);
    this.fallos.update((previos) => ({ ...previos, [nombre]: '' }));

    this.tools.ejecutar(nombre, argumentos).subscribe({
      next: (resultado) => {
        this.resultados.update((previos) => ({ ...previos, [nombre]: resultado }));
        this.ejecutando.set(null);
      },
      error: (fallo: HttpErrorResponse) => {
        this.fallos.update((previos) => ({
          ...previos,
          [nombre]: mensajeDeEjecucion(fallo),
        }));
        this.ejecutando.set(null);
      },
    });
  }

  resultadoDe(nombre: string): ExecuteResult | null {
    return this.resultados()[nombre] ?? null;
  }

  falloDe(nombre: string): string {
    return this.fallos()[nombre] ?? '';
  }

  /** La salida en crudo: no se sabe qué forma tiene cada herramienta. */
  crudoDe(resultado: ExecuteResult): string {
    return JSON.stringify(resultado.data, null, 2);
  }
}
