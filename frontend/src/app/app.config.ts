import { provideHttpClient } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // `withComponentInputBinding` hace que un `:id` de la ruta llegue al
    // `input()` que se llame igual. La alternativa —inyectar
    // `ActivatedRoute` y leer el snapshot— no se entera de que el id
    // cambie sin destruir el componente, que es lo que pasa al ir de
    // /analisis/28 a /analisis/29.
    provideRouter(routes, withComponentInputBinding()),
    // Sin esto, inyectar `HttpClient` lanza `NullInjectorError` en EJECUCIÓN, no
    // al compilar: la pantalla se monta y revienta al pulsar Analizar.
    //
    provideHttpClient(),
  ],
};
