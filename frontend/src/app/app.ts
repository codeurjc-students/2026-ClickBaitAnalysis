import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ChatService } from './api/chat.service';
import { IndicadorSalud } from './salud/indicador-salud';

/**
 * Cáscara de la aplicación: cabecera y hueco donde el router pinta la pantalla.
 *
 * La navegación sigue al prototipo —Asistente · Analizar · Historial ·
 * Sistema— con una regla: cada pestaña aparece cuando aparece su pantalla. La
 * del asistente, además, **sólo si está configurado** (R6.10): el despliegue
 * tiene que funcionar sin él, y una pestaña que lleva a «no está en este
 * despliegue» no sirve de nada. Si está configurado pero APAGADO sí se enseña:
 * la pantalla explica que se enciende bajo demanda (R6.14).
 *
 * Desde #147 la cabecera lleva además el indicador de salud de las APIs
 * externas. Está aquí y no en una pantalla porque la pregunta —«¿esto falla por
 * mí o por un tercero?»— surge al ver fallar algo en cualquiera de ellas.
 */
@Component({
  imports: [RouterOutlet, RouterLink, RouterLinkActive, IndicadorSalud],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  /** Si hay asistente configurado. Hasta saberlo, no se enseña la pestaña. */
  readonly hayAsistente = signal(false);

  constructor() {
    // Una sola vez, al cargar. Saber que no hay nadie escuchando cuesta
    // 0,2 ms (#181), y si la consulta falla la pestaña se queda oculta: la
    // pantalla sigue en `/asistente` para quien llegue por la URL.
    inject(ChatService)
      .agente()
      .pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe({
        next: (informacion) =>
          this.hayAsistente.set(informacion.availability.status !== 'not_configured'),
        error: () => this.hayAsistente.set(false),
      });
  }
}
