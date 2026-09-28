/**
 * Lo que la pantalla del asistente decide sin Angular: qué se pinta de cada
 * paso de la traza y qué historial se manda con la siguiente pregunta (#191).
 *
 * Suelto, como `sistema/campos.ts`, para probarlo con datos y sin montar un
 * componente.
 */
import type { ChatJob, PasoDeLaTraza, Turno } from '../api/models';
import { comoAnalisis, type AnalisisGuardado, type SenalGuardada } from '../senales/formas';

/** Una pregunta y lo que se sabe de su respuesta hasta ahora. */
export interface Intercambio {
  pregunta: string;
  /** La última lectura de la conversación; `null` hasta la primera. */
  trabajo: ChatJob | null;
  /** Por qué no se pudo hacer o seguir la pregunta, ya redactado. */
  error: string | null;
  /** Cuándo se envió y cuándo llegó la última lectura, en ms del reloj local. */
  enviadaEl: number;
  leidaEl: number | null;
}

/**
 * A partir de cuánto la espera avisa de que puede ir para largo.
 *
 * En la aceptación de #191, una vuelta del modelo tardó 98,8 s en producción
 * —y 96 s otra en #188— mientras las demás rondaban los 10–20 s. Sin nada
 * nuevo en pantalla, se leyó como un cuelgue.
 */
export const ESPERA_LARGA_MS = 60_000;

/** Cómo va una pregunta que todavía no ha terminado, para la línea de espera. */
export interface Espera {
  fase: string;
  lleva: string;
  larga: boolean;
}

/**
 * La fase y el tiempo de una pregunta en marcha (#191).
 *
 * Mientras el modelo razona no llega nada nuevo, y la pantalla tiene que dejar
 * claro que sigue trabajando: en qué está —decidiendo qué consultar, o leyendo
 * lo que devolvió una herramienta— y cuánto lleva. El tiempo se mide con el
 * reloj LOCAL, del envío a la última lectura: con el `created_at` del servidor
 * se colaría la diferencia entre los dos relojes.
 */
export function esperaDe(intercambio: Intercambio): Espera {
  const pasos = intercambio.trabajo?.steps ?? [];
  const ultimo = pasos.at(-1);
  const fase = !intercambio.trabajo
    ? 'Enviando la pregunta'
    : ultimo?.kind === 'tool'
      ? 'Leyendo los resultados y decidiendo el siguiente paso'
      : ultimo?.kind === 'model'
        ? 'Consultando las herramientas'
        : 'Decidiendo qué herramientas usar';
  const transcurrido = Math.max(0, (intercambio.leidaEl ?? intercambio.enviadaEl) - intercambio.enviadaEl);
  return {
    fase,
    lleva: duracionLegible(transcurrido),
    larga: transcurrido >= ESPERA_LARGA_MS,
  };
}

/** «12 s», «1 min», «1 min 20 s». */
export function duracionLegible(milisegundos: number): string {
  const segundos = Math.floor(milisegundos / 1000);
  const minutos = Math.floor(segundos / 60);
  const resto = segundos % 60;
  if (minutos === 0) return `${resto} s`;
  return resto === 0 ? `${minutos} min` : `${minutos} min ${resto} s`;
}

/** Una noticia de `get_nyt_news` o `get_guardian_news`. */
export interface Noticia {
  title: string;
  url: string | null;
  date: string | null;
}

/**
 * Cómo se pinta un paso de la traza. Un objeto plano en vez de una unión para
 * que la plantilla lo lea con `@if`, y en orden de preferencia: si hay tarjeta
 * de señal, eso; si no, un análisis; si no, noticias; y si nada encaja, crudo.
 */
export interface VistaDePaso {
  /** La herramienta, o `null` en una vuelta del modelo. */
  herramienta: string | null;
  /** Lo que pidió el modelo en su vuelta. */
  pide: string[];
  error: string | null;
  senal: SenalGuardada | null;
  analisis: AnalisisGuardado | null;
  noticias: Noticia[] | null;
  crudo: string | null;
}

/**
 * Qué se enseña de un paso.
 *
 * - **Una señal** llega con su tarjeta ya calculada por el backend (`signal`),
 *   con la misma regla de voto que el análisis: aquí no se decide qué es
 *   clickbait (#191).
 * - **`analyze_headline`** devuelve un análisis entero, y se pinta con el mismo
 *   bloque que la pantalla de análisis.
 * - **Lo que no encaja se enseña en crudo**, el `@default` de siempre: omitirlo
 *   sería mentir sobre lo que se consultó.
 */
export function vistaDePaso(paso: PasoDeLaTraza): VistaDePaso {
  const vista: VistaDePaso = {
    herramienta: null,
    pide: [],
    error: null,
    senal: null,
    analisis: null,
    noticias: null,
    crudo: null,
  };

  if (paso.kind === 'model') {
    vista.pide = paso.tool_calls;
    return vista;
  }

  vista.herramienta = paso.name;
  if (paso.status === 'error') {
    vista.error = paso.error ?? 'La herramienta falló sin decir por qué.';
    return vista;
  }
  if (paso.signal) {
    vista.senal = paso.signal;
    return vista;
  }
  vista.analisis = comoAnalisis(paso.data);
  if (vista.analisis) return vista;
  vista.noticias = comoNoticias(paso.data);
  if (vista.noticias) return vista;
  vista.crudo = JSON.stringify(paso.data, null, 2);
  return vista;
}

/**
 * Las noticias de un resultado, si tiene su forma: `{result: [{title, url,
 * date}, …]}`, que es como llega por MCP una herramienta que devuelve una
 * lista.
 *
 * Por la FORMA y no por el nombre de la herramienta, como los guardianes de
 * `senales/datos.ts`: una fuente de noticias nueva se pintaría igual, y una
 * lista de otra cosa —las fichas de `describe_models`— no pasa por aquí.
 */
export function comoNoticias(datos: unknown): Noticia[] | null {
  if (typeof datos !== 'object' || datos === null) return null;
  const { result } = datos as { result?: unknown };
  if (!Array.isArray(result) || result.length === 0) return null;

  const noticias: Noticia[] = [];
  for (const elemento of result) {
    if (typeof elemento !== 'object' || elemento === null) return null;
    const { title, url, date } = elemento as Record<string, unknown>;
    if (typeof title !== 'string') return null;
    noticias.push({
      title,
      url: typeof url === 'string' ? url : null,
      date: typeof date === 'string' ? date : null,
    });
  }
  return noticias;
}

/**
 * El historial que se manda con la siguiente pregunta: el texto de los
 * intercambios TERMINADOS con respuesta, quitando los más antiguos hasta que
 * quepa en `tope` (`max_history_chars` de `GET /agent`).
 *
 * Sólo el texto, sin resultados de herramientas (decidido al definir H5). Y se
 * recorta aquí, ANTES de enviar: un historial que desborde la ventana del
 * modelo lo recortaría Ollama en silencio, y el backend lo rechaza con un 422
 * para que no llegue (#189).
 *
 * Se quita por parejas —pregunta y respuesta—, para que el modelo no lea una
 * respuesta sin la pregunta que la originó.
 */
export function historialQueCabe(intercambios: Intercambio[], tope: number): Turno[] {
  const parejas: Turno[][] = [];
  for (const intercambio of intercambios) {
    const respuesta = intercambio.trabajo?.result?.answer.trim();
    if (intercambio.trabajo?.status !== 'done' || !respuesta) continue;
    parejas.push([
      { role: 'user', content: intercambio.pregunta },
      { role: 'assistant', content: respuesta },
    ]);
  }

  const medir = (pareja: Turno[]) =>
    pareja.reduce((suma, turno) => suma + turno.content.length, 0);
  let total = parejas.reduce((suma, pareja) => suma + medir(pareja), 0);
  while (parejas.length > 0 && total > tope) {
    total -= medir(parejas.shift()!);
  }
  return parejas.flat();
}

/** Si la respuesta se apoyó en alguna herramienta (pendiente de #188). */
export function usoHerramientas(trabajo: ChatJob): boolean {
  return trabajo.steps.some((paso) => paso.kind === 'tool');
}
