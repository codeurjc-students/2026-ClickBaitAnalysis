/**
 * Lo que la pantalla del asistente decide sin Angular: qué se pinta de cada
 * paso de la traza y qué historial se manda con la siguiente pregunta (#191),
 * y qué se guarda para que la conversación sobreviva a recargar (#209).
 *
 * Suelto, como `sistema/campos.ts`, para probarlo con datos y sin montar un
 * componente.
 */
import type { ChatJob, PasoDeLaTraza, Turno } from '../api/models';
import { comoAnalisis, type AnalisisGuardado, type SenalGuardada } from '../senales/formas';

/** Una pregunta y lo que se sabe de su respuesta hasta ahora. */
export interface Intercambio {
  pregunta: string;
  /**
   * El id de la conversación en el servidor, en cuanto `POST /chat` la acepta;
   * `null` hasta entonces. Es lo que permite seguirla tras recargar (#209).
   */
  id: string | null;
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
 * Sin resultados de herramientas (decidido al definir H5), pero cada respuesta
 * con los NOMBRES de las que usó (#192): con sólo el texto, el modelo veía
 * respuestas con veredictos y ninguna llamada delante, y en un turno nuevo
 * traía la noticia y se inventaba el análisis sin llamar a ninguna señal.
 *
 * Se recorta aquí, ANTES de enviar, con los nombres dentro de la cuenta como
 * hace el backend: un historial que desborde la ventana del modelo lo
 * recortaría Ollama en silencio, y el backend lo rechaza con un 422 para que
 * no llegue (#189). Se quita por parejas —pregunta y respuesta—, para que el
 * modelo no lea una respuesta sin la pregunta que la originó.
 */
export function historialQueCabe(intercambios: Intercambio[], tope: number): Turno[] {
  const parejas: Turno[][] = [];
  for (const intercambio of intercambios) {
    const trabajo = intercambio.trabajo;
    const respuesta = trabajo?.result?.answer.trim();
    if (trabajo?.status !== 'done' || !respuesta) continue;
    const herramientas = herramientasUsadas(trabajo);
    parejas.push([
      { role: 'user', content: intercambio.pregunta },
      herramientas.length > 0
        ? { role: 'assistant', content: respuesta, tools: herramientas }
        : { role: 'assistant', content: respuesta },
    ]);
  }

  const medir = (pareja: Turno[]) =>
    pareja.reduce(
      (suma, turno) =>
        suma +
        turno.content.length +
        (turno.tools ?? []).reduce((nombres, nombre) => nombres + nombre.length, 0),
      0,
    );
  let total = parejas.reduce((suma, pareja) => suma + medir(pareja), 0);
  while (parejas.length > 0 && total > tope) {
    total -= medir(parejas.shift()!);
  }
  return parejas.flat();
}

/**
 * Las herramientas que llamó una respuesta, sin repetir y en el orden en que
 * se llamaron. También las que fallaron: la llamada existió, y el modelo la vio.
 */
export function herramientasUsadas(trabajo: ChatJob): string[] {
  const nombres = trabajo.steps.flatMap((paso) => (paso.kind === 'tool' ? [paso.name] : []));
  return [...new Set(nombres)];
}

/** Si la respuesta se apoyó en alguna herramienta (pendiente de #188). */
export function usoHerramientas(trabajo: ChatJob): boolean {
  return trabajo.steps.some((paso) => paso.kind === 'tool');
}

/**
 * Si la traza tiene algo que enseñar: una herramienta, o una vuelta del modelo
 * que pidió alguna. Una vuelta que contesta sin pedir nada no pinta nada, y sin
 * esto la lista salía vacía, como un «1.» suelto (visto probando #209).
 */
export function trazaVisible(trabajo: ChatJob): boolean {
  return trabajo.steps.some((paso) => paso.kind === 'tool' || paso.tool_calls.length > 0);
}

/** Si la pregunta está todavía en marcha: ni ha terminado ni ha fallado. */
export function aMedias(intercambio: Intercambio): boolean {
  return !intercambio.error && intercambio.trabajo?.status !== 'done';
}

// ----- Lo que sobrevive a recargar (#209) -----

/**
 * Dónde se guarda la conversación, en `sessionStorage`: dura lo que la pestaña
 * y no sale del navegador. La versión va en la clave: si la forma de lo
 * guardado cambia de verdad, se sube, y lo viejo se ignora entero en vez de
 * leerse a medias.
 */
export const CLAVE_GUARDADO = 'asistente.conversacion.v1';

/**
 * Cuánto se guarda como mucho, en caracteres de JSON: una quinta parte de los
 * ~5 MB que dan los navegadores por origen. Medido con
 * `spikes/historial_tamano.py` sobre 228 conversaciones de #192: un intercambio
 * ocupa 2.422 caracteres de mediana y 21.174 el mayor, así que caben unos 400.
 */
export const TOPE_GUARDADO = 1_000_000;

/** Por qué se perdió una pregunta que el servidor no llegó a aceptar. */
export const PERDIDA_AL_SALIR =
  'Se salió de la página antes de que el asistente aceptara la pregunta. Vuelve a preguntar.';

/**
 * La conversación en JSON, quitando intercambios ENTEROS, de los más antiguos,
 * hasta que quepa en `tope`; y cuántos han cabido, que es lo que dice si hay
 * que avisar de que algo no se conserva. El texto es el mismo que daría
 * `JSON.stringify` de la lista: cada intercambio se serializa una sola vez.
 */
export function paraGuardar(
  intercambios: Intercambio[],
  tope = TOPE_GUARDADO,
): { texto: string; guardados: number } {
  const piezas = intercambios.map((intercambio) => JSON.stringify(intercambio));
  let caracteres = 2; // los corchetes
  let desde = piezas.length;
  while (desde > 0) {
    const coma = desde < piezas.length ? 1 : 0;
    const conEste = caracteres + piezas[desde - 1].length + coma;
    if (conEste > tope) break;
    caracteres = conEste;
    desde -= 1;
  }
  return { texto: `[${piezas.slice(desde).join(',')}]`, guardados: piezas.length - desde };
}

/**
 * Lo guardado, leído con cuidado: puede venir de una versión anterior de la
 * pantalla, o estar roto. Como `comoAnalisis` con el historial, lo que la
 * plantilla no sabría pintar se descarta, intercambio a intercambio, y lo demás
 * se queda. Se miran los campos que lee la pantalla; lo de dentro del `data` de
 * cada paso ya es opcional para quien lo pinta.
 */
export function comoIntercambios(texto: string | null): Intercambio[] {
  if (texto === null) return [];
  let datos: unknown;
  try {
    datos = JSON.parse(texto);
  } catch {
    return [];
  }
  return Array.isArray(datos) ? datos.filter(esIntercambio) : [];
}

/**
 * Lo recuperado, listo para pintarse. Una pregunta a medias con id se deja como
 * está, y la pantalla la vuelve a sondear: el servidor siguió trabajando, y la
 * sirve hasta 15 minutos después de terminar. Sin id —se salió entre el
 * «Enviar» y la respuesta de `POST /chat`— no hay con qué preguntar por ella,
 * y se dice.
 */
export function alRecuperar(intercambios: Intercambio[]): Intercambio[] {
  return intercambios.map((intercambio) =>
    aMedias(intercambio) && intercambio.id === null
      ? { ...intercambio, error: PERDIDA_AL_SALIR }
      : intercambio,
  );
}

/**
 * Qué decir si no se guarda todo lo que se ve, o `null`. Sin almacenamiento
 * —navegación privada, bloqueado o lleno— no se guarda nada; con el tope,
 * faltan los más antiguos. En los dos casos la pantalla lo enseña todo hasta
 * que se recarga o se cambia de sección, y por eso se avisa.
 */
export function avisoDeGuardado(
  enPantalla: number,
  guardados: number,
  almacenamiento: boolean,
): string | null {
  const cuando = 'si recargas la página o vas a otra sección';
  if (enPantalla === 0) return null;
  if (!almacenamiento) return `Este navegador no deja guardar la conversación: se perderá ${cuando}.`;
  const fuera = enPantalla - guardados;
  if (fuera <= 0) return null;
  return fuera === 1
    ? `La pregunta más antigua ya no se guarda, por espacio: se perderá ${cuando}.`
    : `Las ${fuera} preguntas más antiguas ya no se guardan, por espacio: se perderán ${cuando}.`;
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

function esIntercambio(valor: unknown): valor is Intercambio {
  if (!esObjeto(valor)) return false;
  const { pregunta, id, trabajo, error, enviadaEl, leidaEl } = valor;
  return (
    typeof pregunta === 'string' &&
    (id === null || typeof id === 'string') &&
    (error === null || typeof error === 'string') &&
    typeof enviadaEl === 'number' &&
    (leidaEl === null || typeof leidaEl === 'number') &&
    (trabajo === null || esTrabajo(trabajo))
  );
}

const ESTADOS_DEL_TRABAJO: readonly unknown[] = ['queued', 'running', 'done'];

function esTrabajo(valor: unknown): boolean {
  if (!esObjeto(valor)) return false;
  const { id, status, steps, result } = valor;
  return (
    typeof id === 'string' &&
    ESTADOS_DEL_TRABAJO.includes(status) &&
    Array.isArray(steps) &&
    steps.every(esPaso) &&
    (result === null ||
      (esObjeto(result) && typeof result['status'] === 'string' && typeof result['answer'] === 'string'))
  );
}

function esPaso(valor: unknown): boolean {
  if (!esObjeto(valor)) return false;
  if (valor['kind'] === 'model') {
    const pedidas = valor['tool_calls'];
    return Array.isArray(pedidas) && pedidas.every((nombre) => typeof nombre === 'string');
  }
  if (valor['kind'] === 'tool') {
    const senal = valor['signal'];
    return (
      typeof valor['name'] === 'string' &&
      typeof valor['status'] === 'string' &&
      (senal === null || senal === undefined || esObjeto(senal))
    );
  }
  return false;
}
