import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      // La plantilla usa `routerLink`, que no funciona sin un Router. Con la
      // tabla vacía basta: aquí no se navega, sólo se pinta la cáscara.
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('se crea', () => {
    expect(TestBed.createComponent(App).componentInstance).toBeTruthy();
  });

  it('pinta la cabecera con la marca', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();

    const html = fixture.nativeElement as HTMLElement;
    expect(html.querySelector('.marca')?.textContent).toContain(
      'ClickBait Analysis',
    );
  });

  // La regla de la cáscara es que una pestaña sólo existe si existe su
  // pantalla. Este test la sostiene: al añadir la tercera (#129) hay que
  // tocarlo, que es justo el momento de comprobar que la ruta ya está.
  it('enseña una pestaña por cada pantalla que existe', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();

    const html = fixture.nativeElement as HTMLElement;
    const pestanas = [...html.querySelectorAll('.nav a')].map((enlace) => ({
      texto: enlace.textContent?.trim(),
      destino: enlace.getAttribute('href'),
    }));

    expect(pestanas).toEqual([
      { texto: 'Analizar', destino: '/analizar' },
      { texto: 'Sistema', destino: '/sistema' },
    ]);
  });

  it('deja un hueco donde el router pinta la pantalla', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();

    const html = fixture.nativeElement as HTMLElement;
    expect(html.querySelector('router-outlet')).not.toBeNull();
  });
});
