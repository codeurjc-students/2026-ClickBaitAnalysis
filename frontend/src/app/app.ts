import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { IndicadorSalud } from './salud/indicador-salud';

/**
 * Cáscara de la aplicación: cabecera y hueco donde el router pinta la pantalla.
 *
 * La navegación del prototipo tiene cuatro pestañas (Chat · Analizar ·
 * Historial · Sistema) y aquí hay tres: falta el Chat del agente (R13). Enlaces a rutas que no existen serían deuda visible, así que
 * cada pestaña aparece cuando aparece su pantalla.
 *
 * Desde #147 la cabecera lleva además el indicador de salud de las APIs
 * externas. Está aquí y no en una pantalla porque la pregunta —«¿esto falla por
 * mí o por un tercero?»— surge al ver fallar algo en cualquiera de las tres.
 */
@Component({
  imports: [RouterOutlet, RouterLink, RouterLinkActive, IndicadorSalud],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {}
