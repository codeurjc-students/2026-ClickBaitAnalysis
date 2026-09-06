import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

/**
 * Cáscara de la aplicación: cabecera y hueco donde el router pinta la pantalla.
 *
 * La navegación del prototipo tiene cuatro pestañas (Chat · Analizar ·
 * Historial · Sistema) y aquí hay tres: falta el Chat del agente (R13). Enlaces a rutas que no existen serían deuda visible, así que
 * cada pestaña aparece cuando aparece su pantalla.
 */
@Component({
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {}
