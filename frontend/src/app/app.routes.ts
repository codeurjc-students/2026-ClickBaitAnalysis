import { Routes } from '@angular/router';

/**
 * UNA sola ruta de análisis, no dos.
 *
 * El prototipo dibuja «Analizar» y «Resultados» como pantallas separadas, pero
 * como RUTAS no se sostienen hoy: `POST /analyze` no devuelve ningún id
 * (issue #133), así que `/resultados` no sería enlazable ni sobreviviría a una
 * recarga, y obligaría a un servicio de estado cuyo único cometido sería cruzar
 * la navegación. El formulario se pliega en su sitio y el «Nuevo análisis» pasa
 * de navegar a restablecer.
 *
 * Con #133 hecha, `/analisis/:id` se AÑADIÓ sin tocar nada de lo demás, como
 * estaba previsto: resuelve la entrada del historial y alimenta al mismo
 * componente, que ya recibía el análisis como estado. Las dos rutas comparten
 * pantalla a propósito — lo único distinto es de dónde sale el resultado.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'analizar' },
  {
    path: 'analizar',
    title: 'Analizar un titular · ClickBait Analysis',
    // `loadComponent` y no un import normal: la pantalla se descarga cuando se
    // visita. Con una sola ruta daba igual; con la de Sistema detrás ya no, y
    // se ve en el empaquetado (21,69 kB en su propio fragmento).
    loadComponent: () =>
      import('./analisis/analisis-page').then((modulo) => modulo.AnalisisPage),
  },
  {
    // El id llega como `input()` de `AnalisisPage`, no como parámetro leído
    // a mano. La pantalla es la MISMA: sólo cambia de dónde sale el
    // análisis, y por eso #127 la dejó recibiendo el resultado como estado
    // en vez de calcularlo en el sitio.
    path: 'analisis/:id',
    title: 'Análisis guardado · ClickBait Analysis',
    loadComponent: () =>
      import('./analisis/analisis-page').then((modulo) => modulo.AnalisisPage),
  },
  {
    path: 'historial',
    title: 'Historial · ClickBait Analysis',
    loadComponent: () =>
      import('./historial/historial-page').then(
        (modulo) => modulo.HistorialPage,
      ),
  },
  {
    path: 'sistema',
    title: 'Sistema · ClickBait Analysis',
    // Aquí sí se nota la carga diferida que #126 dejó preparada: esta pantalla
    // arrastra el formulario generado y no la necesita quien sólo analiza.
    loadComponent: () =>
      import('./sistema/sistema-page').then((modulo) => modulo.SistemaPage),
  },
  // Cualquier otra cosa a la pantalla que existe. Cuando haya más rutas esto
  // debería ser un 404 de verdad, que es información; hoy sería una pantalla
  // vacía para decir lo mismo.
  { path: '**', redirectTo: 'analizar' },
];
