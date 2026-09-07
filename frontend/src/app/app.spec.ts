import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        // La plantilla usa `routerLink`, que no funciona sin un Router. Con la
        // tabla vacía basta: aquí no se navega, sólo se pinta la cáscara.
        provideRouter([]),
        // Desde #147 la cáscara monta el indicador de salud, que consulta al
        // construirse. Sin esto los tests de la cabecera fallarían por una
        // dependencia que no es suya — el precio de meter algo con estado en la
        // cáscara, y la razón de que el indicador tenga su propio spec.
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
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
      { texto: 'Historial', destino: '/historial' },
      { texto: 'Sistema', destino: '/sistema' },
    ]);
  });

  // El indicador va en la cabecera pero FUERA del `nav`: no es un destino, y
  // dentro se anunciaría como una pestaña más a quien navegue por landmarks.
  it('lleva el indicador de salud en la cabecera, fuera de la navegación', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();

    const html = fixture.nativeElement as HTMLElement;
    expect(html.querySelector('.cabecera app-indicador-salud')).not.toBeNull();
    expect(html.querySelector('.nav app-indicador-salud')).toBeNull();
  });

  it('deja un hueco donde el router pinta la pantalla', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();

    const html = fixture.nativeElement as HTMLElement;
    expect(html.querySelector('router-outlet')).not.toBeNull();
  });
});
