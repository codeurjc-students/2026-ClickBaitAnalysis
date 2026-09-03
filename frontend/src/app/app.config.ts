import { provideHttpClient } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    // Sin esto, inyectar `HttpClient` lanza `NullInjectorError` en EJECUCIÓN, no
    // al compilar: la pantalla se monta y revienta al pulsar Analizar.
    //
    provideHttpClient(),
  ],
};
