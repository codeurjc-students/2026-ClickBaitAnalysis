// #216 (22 nov 2026) - R6.8 sobre la versión congelada: qué se sale de la
// ventana a 768 y a 1.024 píxeles, en cada pantalla de producción.
//
// R6.8 pide que la interfaz funcione en escritorio y en tabletas. #130 y #147
// lo midieron a 768 y 1.024 px en cuatro rutas, comprobando qué elemento
// sobresale de la ventana, y no lo dejaron en un guion. El repaso preliminar
// de #216 dejó sin medir la pantalla del asistente y la cabecera con sus cuatro
// pestañas. Este guion lo mide todo con la misma regla:
//
// - **Lo que se sale**: cada elemento visible cuya caja pasa del borde de la
//   ventana, contando sólo el más externo de cada rama. Lo que está dentro de un
//   contenedor con desplazamiento propio (`overflow-x` distinto de `visible`)
//   que sí cabe no se sale: se cuenta aparte, porque se lee desplazando ese
//   contenedor y no la página.
// - **La cabecera**: su alto y en cuántas filas salen las pestañas del `nav`.
// - **La página**: su alto, porque lo que no se sale a lo ancho crece a lo alto
//   (#130: la tabla del historial, un 51 %).
//
// Se mide a 768×1024 (tableta en vertical), 1024×768 (en horizontal) y
// 1280×800 (escritorio, de control). Usa el mismo Edge de Windows sin ventana
// que `spikes/capturas.mjs`, por el protocolo de DevTools, y se para si la
// máquina 1 no sirve el commit que se le da.
//
// Dos recorridos:
//
// - `rutas` (el de por defecto): `/analizar`, el último análisis del historial
//   en `/analisis/:id`, `/historial`, `/sistema`, la salud desplegada y
//   `/asistente` tal como esté. No escribe nada en producción.
// - `asistente`: con el asistente disponible (el modelo o las respuestas
//   grabadas, `compose.grabado.yaml`), hace las tres preguntas del paso 6 de
//   `docs/demostracion.md` y mide la conversación, con las tarjetas plegadas y
//   abiertas. No guarda nada en el historial.
//
// Ejecutar desde PowerShell, con el Node de Windows (22 o posterior):
//   node \\wsl.localhost\ubuntu\home\ggarciac\TFG\2026-ClickBaitAnalysis\spikes\anchos_r68.mjs 79f029e [rutas|asistente] [fichero]
// Con un fichero, además de imprimirla, le añade la salida al final.

import { spawn, spawnSync } from 'node:child_process';
import {
  appendFileSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { setTimeout as esperar } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const SITIO = 'https://gongarcia.tfg.etsii.urjc.es';
const MAQUINA_1 = 'tfg-app';
const CLON = '~/2026-ClickBaitAnalysis';
const VENTANAS = [
  { ancho: 768, alto: 1024 },
  { ancho: 1024, alto: 768 },
  { ancho: 1280, alto: 800 },
];
const TOPE_TURNO = 600000;
const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '..');

const [esperado, recorrido = 'rutas', fichero = null] = process.argv.slice(2);
if (!esperado || !['rutas', 'asistente'].includes(recorrido)) {
  console.error('Uso: node spikes/anchos_r68.mjs <commit> [rutas|asistente] [fichero]');
  process.exit(2);
}

function escribir(linea = '') {
  console.log(linea);
  if (fichero) appendFileSync(fichero, `${linea}\n`);
}

function compararVersiones(primera, segunda) {
  const partesPrimera = primera.split('.').map(Number);
  const partesSegunda = segunda.split('.').map(Number);
  const largo = Math.max(partesPrimera.length, partesSegunda.length);
  for (let posicion = 0; posicion < largo; posicion++) {
    const diferencia = (partesPrimera[posicion] ?? 0) - (partesSegunda[posicion] ?? 0);
    if (diferencia) return diferencia;
  }
  return 0;
}

function buscarEdge() {
  if (process.env.EDGE) return process.env.EDGE;
  const microsoft = 'C:\\Program Files (x86)\\Microsoft';
  const nucleo = join(microsoft, 'EdgeCore');
  const versiones = existsSync(nucleo)
    ? readdirSync(nucleo).filter((version) => existsSync(join(nucleo, version, 'msedge.exe')))
    : [];
  if (versiones.length) {
    versiones.sort(compararVersiones);
    return join(nucleo, versiones.at(-1), 'msedge.exe');
  }
  const aplicacion = join(microsoft, 'Edge', 'Application', 'msedge.exe');
  if (existsSync(aplicacion)) return aplicacion;
  throw new Error('No encuentro msedge.exe: dalo con $env:EDGE');
}

function commitServido() {
  const respuesta = spawnSync(
    'ssh',
    ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', MAQUINA_1, `git -C ${CLON} rev-parse HEAD`],
    { encoding: 'utf8', timeout: 30000 },
  );
  if (respuesta.status !== 0) {
    throw new Error(`no pude preguntar a la máquina 1: ${respuesta.stderr || respuesta.error}`);
  }
  return respuesta.stdout.trim();
}

// Las tres preguntas del paso 6, tal como las da la guía de la demostración.
function preguntasDeLaGuia() {
  const guia = readFileSync(join(RAIZ, 'docs', 'demostracion.md'), 'utf8').replace(/\r/g, '');
  const desde = guia.indexOf('Las tres preguntas del paso 6:');
  if (desde < 0) throw new Error('docs/demostracion.md ya no tiene «Las tres preguntas del paso 6»');
  const bloques = [...guia.slice(desde).matchAll(/```text\n([^\n]+)\n```/g)].map(
    (bloque) => bloque[1],
  );
  if (bloques.length < 3) throw new Error('no encuentro las tres preguntas del paso 6');
  return bloques.slice(0, 3);
}

async function json(ruta) {
  return (await fetch(`${SITIO}${ruta}`, { signal: AbortSignal.timeout(15000) })).json();
}

const servido = commitServido();
if (!servido.startsWith(esperado)) {
  console.error(`La máquina 1 sirve ${servido.slice(0, 7)}, no ${esperado}: no se mide.`);
  process.exit(1);
}
const contrato = await json('/api/openapi.json');
const agente = await json('/api/agent');
if (recorrido === 'asistente' && agente.availability.status !== 'available') {
  console.error(`El asistente está ${agente.availability.status}: no hay conversación que medir.`);
  process.exit(1);
}

const perfil = mkdtempSync(join(tmpdir(), 'anchos-edge-'));
const navegador = spawn(
  buscarEdge(),
  [
    '--headless=new',
    '--remote-debugging-port=0',
    `--user-data-dir=${perfil}`,
    '--window-size=1280,800',
    '--hide-scrollbars',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--lang=es-ES',
    'about:blank',
  ],
  { stdio: 'ignore' },
);
const cerrado = new Promise((resolver) => navegador.once('exit', resolver));

// Con el puerto 0, el navegador elige uno libre y lo escribe en su perfil.
async function paginaDeDepuracion() {
  const puertoActivo = join(perfil, 'DevToolsActivePort');
  for (let intento = 0; intento < 100; intento++) {
    if (existsSync(puertoActivo)) {
      const [puerto] = readFileSync(puertoActivo, 'utf8').split('\n');
      try {
        const lista = await (await fetch(`http://127.0.0.1:${puerto}/json/list`)).json();
        const pagina = lista.find((entrada) => entrada.type === 'page');
        if (pagina) return pagina.webSocketDebuggerUrl;
      } catch {
        // todavía arrancando
      }
    }
    await esperar(200);
  }
  throw new Error('Edge no abrió el puerto de depuración');
}

let direccion;
try {
  direccion = await paginaDeDepuracion();
} catch (error) {
  navegador.kill();
  throw error;
}
const conexion = new WebSocket(direccion);
await new Promise((resolver) => conexion.addEventListener('open', resolver, { once: true }));
let siguiente = 1;
const pendientes = new Map();
conexion.addEventListener('message', (evento) => {
  const mensaje = JSON.parse(evento.data);
  if (mensaje.id && pendientes.has(mensaje.id)) {
    const { resolver, rechazar } = pendientes.get(mensaje.id);
    pendientes.delete(mensaje.id);
    if (mensaje.error) rechazar(new Error(JSON.stringify(mensaje.error)));
    else resolver(mensaje.result);
  }
});

function cdp(metodo, parametros = {}) {
  const identificador = siguiente++;
  conexion.send(JSON.stringify({ id: identificador, method: metodo, params: parametros }));
  return new Promise((resolver, rechazar) =>
    pendientes.set(identificador, { resolver, rechazar }),
  );
}

async function evaluar(expresion) {
  const respuesta = await cdp('Runtime.evaluate', {
    expression: expresion,
    awaitPromise: true,
    returnByValue: true,
  });
  if (respuesta.exceptionDetails) throw new Error(JSON.stringify(respuesta.exceptionDetails));
  return respuesta.result.value;
}

async function hasta(condicion, descripcion, tope = 60000) {
  const inicio = Date.now();
  while (Date.now() - inicio < tope) {
    if (await evaluar(condicion)) return;
    await esperar(250);
  }
  throw new Error(`no llegó: ${descripcion}`);
}

async function ventana({ ancho, alto }) {
  await cdp('Emulation.setDeviceMetricsOverride', {
    width: ancho,
    height: alto,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await esperar(700);
}

async function ir(ruta, condicion) {
  await cdp('Page.navigate', { url: `${SITIO}${ruta}` });
  await hasta(condicion, ruta);
  await esperar(1000);
}

// Pulsa el primer botón cuyo texto contiene el dado.
async function pulsar(texto) {
  const hecho = await evaluar(`(() => {
    const boton = [...document.querySelectorAll('button')].find((candidato) =>
      candidato.textContent.replace(/\\s+/g, ' ').includes(${JSON.stringify(texto)}));
    if (!boton) return false;
    boton.click();
    return true;
  })()`);
  if (!hecho) throw new Error(`no hay botón con «${texto}»`);
  await esperar(500);
}

// La medida, dentro de la página. Devuelve lo que se sale, lo que queda en un
// contenedor con desplazamiento, la cabecera y el alto.
const MEDIR = `(() => {
  const ancho = document.documentElement.clientWidth;
  const describir = (elemento) =>
    elemento.tagName.toLowerCase() +
    (elemento.id ? '#' + elemento.id : '') +
    [...elemento.classList].map((clase) => '.' + clase).join('');
  const contenedor = (elemento) => {
    for (let padre = elemento.parentElement; padre && padre !== document.body; padre = padre.parentElement) {
      if (getComputedStyle(padre).overflowX !== 'visible') return padre;
    }
    return null;
  };
  const fuera = [];
  const desplazables = new Set();
  for (const elemento of document.body.querySelectorAll('*')) {
    const caja = elemento.getBoundingClientRect();
    if (caja.width === 0 || caja.height === 0) continue;
    if (caja.right <= ancho + 0.5 && caja.left >= -0.5) continue;
    const propio = contenedor(elemento);
    if (propio && propio.getBoundingClientRect().right <= ancho + 0.5) {
      desplazables.add(describir(propio));
      continue;
    }
    fuera.push(elemento);
  }
  const externos = fuera.filter((elemento) => !fuera.includes(elemento.parentElement));
  const cabecera = document.querySelector('header.cabecera');
  const filas = new Set(
    [...document.querySelectorAll('header.cabecera nav a')].map((enlace) =>
      Math.round(enlace.getBoundingClientRect().top),
    ),
  );
  return {
    ancho,
    scroll: document.documentElement.scrollWidth,
    fuera: externos.map(
      (elemento) => describir(elemento) + ' +' + Math.round(elemento.getBoundingClientRect().right - ancho) + ' px',
    ),
    desplazables: [...desplazables],
    cabecera: cabecera ? Math.round(cabecera.getBoundingClientRect().height) : null,
    pestanas: document.querySelectorAll('header.cabecera nav a').length,
    filas: filas.size,
    alto: document.documentElement.scrollHeight,
  };
})()`;

async function medir(nombre) {
  const medida = await evaluar(MEDIR);
  const fuera = medida.fuera.length ? medida.fuera.join(', ') : 'nada';
  const desplazables = medida.desplazables.length
    ? ` · con desplazamiento propio: ${medida.desplazables.join(', ')}`
    : '';
  escribir(
    `  ${nombre.padEnd(28)} ${String(medida.ancho).padStart(4)} px · se sale: ${fuera}${desplazables}` +
      ` · cabecera ${medida.cabecera} px, ${medida.pestanas} pestañas en ${medida.filas} fila(s)` +
      ` · alto ${medida.alto} px`,
  );
  return medida;
}

async function recorrerRutas() {
  const historial = await json('/api/history?limit=50');
  const analisis = historial.items.find((entrada) => entrada.kind === 'analysis');
  for (const medidas of VENTANAS) {
    await ventana(medidas);
    escribir(`== ${medidas.ancho}×${medidas.alto}`);
    await ir('/analizar', "!!document.querySelector('button[type=submit]')");
    await medir('/analizar');
    if (analisis) {
      await ir(`/analisis/${analisis.id}`, "!!document.querySelector('.veredicto')");
      await medir(`/analisis/${analisis.id}`);
    }
    await ir('/historial', "document.querySelectorAll('tbody tr').length > 0");
    await medir('/historial');
    await ir('/sistema', "document.querySelectorAll('.tool').length > 0");
    await medir('/sistema');
    await evaluar("document.querySelector('.salud .pastilla').click()");
    await hasta("document.body.innerText.includes('Comprobado a las')", 'la salud');
    await esperar(500);
    await medir('/sistema, salud desplegada');
    await ir('/asistente', 'document.body.innerText.length > 200');
    await esperar(1500);
    await medir(`/asistente (${agente.availability.status})`);
  }
}

// Manda una pregunta y espera a que el turno acabe, con respuesta o sin ella.
async function preguntar(pregunta, numero) {
  const antes = await evaluar("document.querySelectorAll('li.intercambio').length");
  await evaluar(`(() => {
    const campo = document.querySelector('#mensaje');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(campo, ${JSON.stringify(pregunta)});
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('form button[type=submit]').click();
  })()`);
  await hasta(
    `document.querySelectorAll('li.intercambio').length === ${antes + 1}`,
    `la pregunta ${numero} en la conversación`,
    10000,
  );
  await hasta(
    `(() => {
      const ultimo = [...document.querySelectorAll('li.intercambio')].at(-1);
      return !ultimo.querySelector('.espera') && !document.querySelector('form button[type=submit]').disabled;
    })()`,
    `la respuesta ${numero}`,
    TOPE_TURNO,
  );
  const estado = await evaluar(
    "[...document.querySelectorAll('li.intercambio')].at(-1).querySelector('.narracion') ? 'respondió' : 'sin respuesta escrita'",
  );
  escribir(`  turno ${numero}: ${estado}`);
}

async function recorrerAsistente() {
  await ventana(VENTANAS[0]);
  await ir('/asistente', "!!document.querySelector('#mensaje')");
  for (const [posicion, pregunta] of preguntasDeLaGuia().entries()) {
    await preguntar(pregunta, posicion + 1);
  }
  for (const medidas of VENTANAS) {
    await ventana(medidas);
    escribir(`== ${medidas.ancho}×${medidas.alto}`);
    await medir('/asistente, conversación');
  }
  await evaluar(
    `document.querySelectorAll('.tarjeta button.cabecera[aria-expanded="false"]').forEach((cabecera) => cabecera.click())`,
  );
  await esperar(800);
  for (const medidas of VENTANAS) {
    await ventana(medidas);
    escribir(`== ${medidas.ancho}×${medidas.alto}, con las tarjetas abiertas`);
    await medir('/asistente, conversación');
  }
  await pulsar('Empezar una conversación nueva');
}

try {
  await cdp('Page.enable');
  await cdp('Runtime.enable');
  await cdp('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-color-scheme', value: 'light' }],
  });
  const { product } = await cdp('Browser.getVersion');
  escribir(
    `== ${new Date().toLocaleString('sv-SE', { timeZone: 'Europe/Madrid' })} · ${recorrido} · ${product}` +
      ` · la máquina 1 sirve ${servido.slice(0, 7)} · contrato ${contrato.info.version}` +
      ` · asistente ${agente.availability.status}` +
      (agente.recording ? ' (respuestas grabadas)' : ''),
  );
  if (recorrido === 'asistente') await recorrerAsistente();
  else await recorrerRutas();
} catch (error) {
  escribir(`FALLÓ: ${error.message}`);
  process.exitCode = 1;
} finally {
  // Si el navegador se cierra antes de contestar, la respuesta no llega nunca.
  await Promise.race([cdp('Browser.close').catch(() => {}), esperar(2000)]);
  conexion.close();
  await Promise.race([cerrado, esperar(5000)]);
  navegador.kill();
  try {
    rmSync(perfil, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
  } catch (error) {
    console.error(`No pude borrar ${perfil}: ${error.message}`);
  }
}
