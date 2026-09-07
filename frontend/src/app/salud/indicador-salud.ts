import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';

import { SIN_RESPUESTA } from '../api/errores';
import { HealthService } from '../api/health.service';
import type { HealthResult, Sonda } from '../api/models';

/**
 * Los cinco estados que puede enseñar el indicador.
 *
 * Son los tres del backend más dos que el backend no puede contar: que la
 * consulta está en marcha, y que **no contestó nadie**. El último es el que
 * obliga a tener un tipo propio: `down` significa «pregunté y ninguna API
 * responde», e `incomunicado` significa «no pude preguntar». Fundirlos pintaría
 * de rojo un backend apagado y mandaría a mirar unas APIs de terceros que
 * probablemente estén perfectamente.
 */
type EstadoIndicador = 'cargando' | 'ok' | 'degraded' | 'down' | 'incomunicado';

/**
 * Lo que se lee en la pastilla. Es la única señal para quien no distingue los
 * colores, así que dice el estado con palabras y no sólo con el punto.
 */
const ETIQUETAS: Record<EstadoIndicador, string> = {
  cargando: 'Comprobando…',
  ok: 'APIs externas ok',
  degraded: 'Alguna API falla',
  down: 'APIs externas caídas',
  incomunicado: 'Sin respuesta',
};

/** La frase que explica el estado al desplegar, ya sin abreviar. */
const EXPLICACIONES: Record<EstadoIndicador, string> = {
  cargando: 'Sondeando las APIs externas…',
  ok: 'Todas las APIs externas respondieron al último sondeo.',
  degraded: 'Alguna API externa no respondió. Las herramientas que dependen de ella fallarán.',
  down: 'Ninguna API externa respondió.',
  incomunicado: 'No se pudo consultar el estado, así que no se sabe cómo están las APIs externas.',
};

/**
 * Nombres presentables de las integraciones que sondea el backend hoy.
 *
 * Con recurso al original: `integrations` es un diccionario ABIERTO, así que
 * una integración nueva llega sin pasar por aquí y se enseña con su clave en
 * crudo. Es el mismo criterio que el `@default` de `senal-card` — lo
 * desconocido **se ve**, aunque se vea feo; omitirlo sería mentir sobre lo que
 * se sondeó.
 */
const NOMBRES: Record<string, string> = {
  weather: 'Weather.gov',
  guardian: 'The Guardian',
  nyt: 'New York Times',
};

/** Una integración lista para pintar, con su clave por si hace falta. */
interface SondaDeIntegracion {
  clave: string;
  nombre: string;
  sonda: Sonda;
}

/**
 * Indicador de salud de las APIs externas, en la cabecera (#147).
 *
 * **Por qué en la cabecera y no en la pantalla de Sistema.** Sistema responde
 * «qué está conectado», que es lo que el sistema *es*; esto responde «qué
 * funciona ahora mismo», que cambia solo. Y sobre todo: la pregunta surge al
 * ver fallar algo en `/analizar` o en el historial, así que la respuesta tiene
 * que estar a la vista desde cualquier pantalla, no a dos clics.
 *
 * **Lo que NO cubre, y está escrito en la propia pastilla al desplegarla:** el
 * backend sondea las APIs de noticias, no las señales NLP. Un verde aquí no
 * dice nada sobre si `detect_clickbait` responde — el 3 de septiembre lo habría
 * dicho toda la mañana con esa señal devolviendo 400. Prometer «estado del
 * sistema» sería peor que no tener indicador. Ver #156.
 */
@Component({
  selector: 'app-indicador-salud',
  templateUrl: './indicador-salud.html',
  styleUrl: './indicador-salud.scss',
})
export class IndicadorSalud {
  private readonly salud = inject(HealthService);

  readonly estadoRecibido = signal<HealthResult | null>(null);
  readonly cargando = signal(false);
  readonly error = signal<string | null>(null);
  readonly abierto = signal(false);

  readonly estado = computed<EstadoIndicador>(() => {
    if (this.cargando()) return 'cargando';
    if (this.error()) return 'incomunicado';
    return this.estadoRecibido()?.status ?? 'incomunicado';
  });

  readonly etiqueta = computed(() => ETIQUETAS[this.estado()]);
  readonly explicacion = computed(() => EXPLICACIONES[this.estado()]);

  /**
   * Las integraciones sondeadas, las que fallan primero.
   *
   * Ordenar por estado y no por nombre es la diferencia entre un panel que se
   * lee y uno que hay que recorrer: lo accionable es lo que está roto, y con
   * una lista corta ordenada alfabéticamente puede quedar la última.
   */
  readonly sondas = computed<SondaDeIntegracion[]>(() => {
    const integraciones = this.estadoRecibido()?.integrations ?? {};

    return Object.entries(integraciones)
      .map(([clave, sonda]) => ({ clave, nombre: NOMBRES[clave] ?? clave, sonda }))
      .sort((primera, segunda) => Number(primera.sonda.reachable) - Number(segunda.sonda.reachable));
  });

  /** La hora del último sondeo, o `null` si todavía no hay ninguno. */
  readonly comprobadoA = computed(() => {
    const marca = this.estadoRecibido()?.timestamp;
    if (!marca) return null;

    const momento = new Date(marca);
    return Number.isNaN(momento.getTime())
      ? null
      : momento.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
  });

  constructor() {
    this.consultar();
  }

  /**
   * Pide el estado. Se llama al montar y desde el botón de volver a comprobar,
   * **nunca en bucle**: cada llamada son tres peticiones HTTP reales contra
   * APIs de terceros con cuota, y es información que cambia despacio.
   */
  consultar(): void {
    if (this.cargando()) return;

    this.cargando.set(true);
    this.error.set(null);

    this.salud.estado().subscribe({
      next: (recibido) => {
        this.estadoRecibido.set(recibido);
        this.cargando.set(false);
      },
      error: (fallo: HttpErrorResponse) => {
        // El estado anterior se descarta: mantenerlo dejaría una hora de
        // sondeo antigua junto a un mensaje de fallo, que es peor que no saber.
        this.estadoRecibido.set(null);
        this.error.set(this.mensajeDeFallo(fallo));
        this.cargando.set(false);
      },
    });
  }

  alternar(): void {
    this.abierto.update((estaAbierto) => !estaAbierto);
  }

  /**
   * **Con la API apagada NO llega `status 0`, llega 502.** Medido el 7-09
   * parando uvicorn con la interfaz delante.
   *
   * La razón es la topología, que es la misma en desarrollo y en despliegue:
   * entre el navegador y la API hay siempre un proxy —`proxy.conf.json` ahora,
   * nginx en H4— y quien contesta cuando el destino no está es el proxy. El
   * `status 0` de `SIN_RESPUESTA` sólo aparecería si no contestara ni él.
   *
   * Por eso los códigos de pasarela se tratan como «no hay API al otro lado» y
   * no como «la API falló»: son cosas distintas para quien mira, y decir «la
   * API no pudo informar de su estado» de un proceso que está apagado es
   * mentir sobre dónde está el problema.
   */
  private mensajeDeFallo(fallo: HttpErrorResponse): string {
    const DE_PASARELA = [502, 503, 504];
    if (fallo.status === 0 || DE_PASARELA.includes(fallo.status)) {
      return SIN_RESPUESTA;
    }
    return `La API no pudo informar de su estado (${fallo.status}).`;
  }
}
