import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import type { AgentInfo, Disponibilidad } from './api/models';
import { App } from './app';

/** Lo que responde `GET /agent`, con el estado que se diga. */
function agente(status: Disponibilidad['status']): AgentInfo {
  return {
    availability: { status, detail: 'Motivo publicable.', model: 'qwen3.5:27b' },
    model_card: {
      model_id: 'qwen3.5:27b',
      name: 'Qwen 3.5, 27B',
      task: 'Narra lo que devuelven las herramientas.',
      type: 'opaque',
      limitations: [],
    },
    prompt: { name: '04-preciso', text: 'Eres el asistente…' },
    max_history_chars: 4000,
  };
}

/** Las pestañas de la cabecera, con su texto y su destino. */
function pestanasDe(html: HTMLElement) {
  return [...html.querySelectorAll('.nav a')].map((enlace) => ({
    texto: enlace.textContent?.trim(),
    destino: enlace.getAttribute('href'),
  }));
}

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
  //
  // La del asistente aparece si está CONFIGURADO, aunque esté apagado: la
  // pantalla explica entonces que se enciende bajo demanda (R6.14, #191).
  it('enseña una pestaña por cada pantalla que existe', async () => {
    const fixture = TestBed.createComponent(App);
    TestBed.inject(HttpTestingController)
      .expectOne('/api/agent')
      .flush(agente('unreachable'));
    await fixture.whenStable();

    expect(pestanasDe(fixture.nativeElement as HTMLElement)).toEqual([
      { texto: 'Asistente', destino: '/asistente' },
      { texto: 'Analizar', destino: '/analizar' },
      { texto: 'Historial', destino: '/historial' },
      { texto: 'Sistema', destino: '/sistema' },
    ]);
  });

  // R6.10: el asistente se ofrece «cuando esté configurado». Sin él, una
  // pestaña que sólo lleva a explicarlo no sirve de nada.
  it('sin asistente configurado no enseña su pestaña', async () => {
    const fixture = TestBed.createComponent(App);
    TestBed.inject(HttpTestingController)
      .expectOne('/api/agent')
      .flush(agente('not_configured'));
    await fixture.whenStable();

    const pestanas = pestanasDe(fixture.nativeElement as HTMLElement);
    expect(pestanas.map((pestana) => pestana.texto)).toEqual([
      'Analizar',
      'Historial',
      'Sistema',
    ]);
  });

  it('si no se puede preguntar por el asistente, tampoco la enseña', async () => {
    const fixture = TestBed.createComponent(App);
    TestBed.inject(HttpTestingController)
      .expectOne('/api/agent')
      .flush(null, { status: 502, statusText: 'Bad Gateway' });
    await fixture.whenStable();

    const pestanas = pestanasDe(fixture.nativeElement as HTMLElement);
    expect(pestanas.some((pestana) => pestana.texto === 'Asistente')).toBe(false);
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
