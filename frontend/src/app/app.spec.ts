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

  it('deja un hueco donde el router pinta la pantalla', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();

    const html = fixture.nativeElement as HTMLElement;
    expect(html.querySelector('router-outlet')).not.toBeNull();
  });
});
