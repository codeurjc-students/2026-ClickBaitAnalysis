// #215 (21 nov 2026) - Las capturas de pantalla de la versión servida.
//
// Las notas `\alumno` de la memoria (el capítulo 3, la descripción funcional) y
// el plan C de `docs/demostracion.md` piden capturas de cada pantalla de la
// versión congelada, tal como la sirve la máquina 1. Una captura es una
// afirmación sobre el sistema, como un ejemplo del formulario (#282): este
// guion las hace todas con el mismo recorrido, para que se puedan repetir y no
// salgan de pulsar a mano.
//
// Por qué así, y no con otra herramienta: el navegador integrado de la app de
// Claude enseña la página pero no guarda la imagen, y en WSL no hay navegador.
// Se usa el Edge de Windows sin ventana (`--headless=new`), manejado por el
// protocolo de DevTools (CDP) desde el Node de Windows, que trae `fetch` y
// `WebSocket` de serie: no hay que instalar nada (ni Puppeteer ni Playwright).
//
// Dos recorridos, porque no pueden hacerse a la vez:
//
// - `pantallas` (el de por defecto), con la GPU APAGADA: el formulario, tres
//   análisis, la salud, el historial, Sistema con una ejecución suelta y el
//   asistente sin el modelo en marcha, que es su estado normal.
// - `asistente`, con una sesión de GPU ABIERTA (`gpu-sesion`, que lleva el
//   túnel a la máquina 1): espera a que `/api/agent` diga `available`, y hace
//   el paso 6 de la demostración como lo pide la guía: las tres preguntas para
//   calentar, «Empezar una conversación nueva» y las tres otra vez. Las
//   preguntas las lee de «Los textos» de `docs/demostracion.md`, así que la
//   captura sigue a la guía. Imprime lo que esperó el navegador en cada turno y
//   el intervalo para `spikes/chat_registro.sh`, que da los tiempos de verdad.
//
// Antes de capturar, pregunta por SSH en qué commit está el clon de la máquina
// 1 (con el alias `tfg-app` del `~/.ssh/config` de Windows) y se para si no es
// el que se le da. La versión del contrato la lee de `/api/openapi.json`.
//
// ⚠️ Escribe en producción. `pantallas`: tres análisis (los botones «clickbait
// claro», «caso ambiguo» y «en español») y una ejecución de
// `analyze_sentiment` desde Sistema, que quedan en el historial, como los de
// `produccion_en_vivo.py`. `asistente`: seis turnos del asistente, que no
// guarda nada en el historial (H5).
//
// Cada recorrido captura primero en una carpeta temporal y, sólo si han salido
// todas, deja sus PNG en `docs/img/capturas/` junto con su lista,
// `<recorrido>.json`, y borra los que su lista anterior tenía y ya no hace. El
// índice, `README.md`, sale de las listas de los dos: lanzar uno no borra lo
// del otro. Nada de esa carpeta se edita a mano. La ventana es de 1280×800
// píxeles CSS a escala 2 (imágenes de 2.560 de ancho, para que se lean
// impresas), con el tema claro y en español.
//
// Ejecutar desde PowerShell, con el Node de Windows (22 o posterior):
//   node \\wsl.localhost\ubuntu\home\ggarciac\TFG\2026-ClickBaitAnalysis\spikes\capturas.mjs 79f029e [pantallas|asistente]
// Usa el Edge más reciente de `EdgeCore` o, si no hay, el de
// `Edge\Application`; con `$env:EDGE = '<ruta de msedge.exe>'`, el que se diga.

import { spawn, spawnSync } from 'node:child_process';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { setTimeout as esperar } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const SITIO = 'https://gongarcia.tfg.etsii.urjc.es';
const MAQUINA_1 = 'tfg-app';
const CLON = '~/2026-ClickBaitAnalysis';
const ANCHO = 1280;
const ALTO = 800;
const ESCALA = 2;
const TITULAR_SISTEMA = "10 Amazing Things You Won't Believe";
// Una vuelta del 27B puede tardar un par de minutos, y la primera carga el
// modelo: el tope de un turno es holgado a propósito.
const TOPE_TURNO = 600000;
const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '..');
const DESTINO = join(RAIZ, 'docs', 'img', 'capturas');

const RECORRIDOS = {
  pantallas: {
    titulo: 'Las pantallas',
    deja:
      'Cada ejecución deja en producción tres análisis y una ejecución suelta, ' +
      'que quedan en el historial.',
  },
  asistente: {
    titulo: 'El asistente, con el modelo en marcha',
    deja:
      'Cada ejecución deja en producción seis turnos del asistente, que no ' +
      'guarda nada en el historial (H5).',
  },
};

const esperado = process.argv[2];
const recorrido = process.argv[3] ?? 'pantallas';
if (!esperado || !(recorrido in RECORRIDOS)) {
  console.error(
    'Uso: node spikes/capturas.mjs <commit que tiene que servir la máquina 1> [pantallas|asistente]',
  );
  process.exit(2);
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

// El commit del clon de la máquina 1 y cuántos ficheros tiene cambiados.
function clonServido() {
  const respuesta = spawnSync(
    'ssh',
    [
      '-o',
      'BatchMode=yes',
      '-o',
      'ConnectTimeout=10',
      MAQUINA_1,
      `git -C ${CLON} rev-parse HEAD && git -C ${CLON} status --porcelain | wc -l`,
    ],
    { encoding: 'utf8', timeout: 30000 },
  );
  if (respuesta.status !== 0) {
    throw new Error(`no pude preguntar a la máquina 1: ${respuesta.stderr || respuesta.error}`);
  }
  const [commit, cambios] = respuesta.stdout.trim().split(/\s+/);
  return { commit, cambios: Number(cambios) };
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

// Pregunta a la API, nunca a la máquina 2, hasta que el asistente esté.
async function esperarAlAsistente(tope = 300000) {
  const inicio = Date.now();
  while (Date.now() - inicio < tope) {
    try {
      const agente = await (
        await fetch(`${SITIO}/api/agent`, { signal: AbortSignal.timeout(15000) })
      ).json();
      if (agente.availability.status === 'available') return agente;
      console.log(`  /api/agent: ${agente.availability.status}`);
    } catch (error) {
      console.log(`  /api/agent no respondió: ${error.message}`);
    }
    await esperar(10000);
  }
  throw new Error('el asistente no estuvo disponible en 5 minutos');
}

const clon = clonServido();
if (!clon.commit.startsWith(esperado)) {
  console.error(`La máquina 1 sirve ${clon.commit.slice(0, 7)}, no ${esperado}: no se captura.`);
  process.exit(1);
}
const contrato = await (
  await fetch(`${SITIO}/api/openapi.json`, { signal: AbortSignal.timeout(15000) })
).json();
let agente = null;
let preguntas = [];
if (recorrido === 'asistente') {
  preguntas = preguntasDeLaGuia();
  agente = await esperarAlAsistente();
  if (agente.recording) {
    console.error('El asistente sirve respuestas grabadas (el plan B), no el modelo: no se captura.');
    process.exit(1);
  }
}

const perfil = mkdtempSync(join(tmpdir(), 'capturas-edge-'));
const temporal = mkdtempSync(join(tmpdir(), 'capturas-png-'));
const navegador = spawn(
  buscarEdge(),
  [
    '--headless=new',
    '--remote-debugging-port=0',
    `--user-data-dir=${perfil}`,
    `--window-size=${ANCHO},${ALTO}`,
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
  const fichero = join(perfil, 'DevToolsActivePort');
  for (let intento = 0; intento < 100; intento++) {
    if (existsSync(fichero)) {
      const [puerto] = readFileSync(fichero, 'utf8').split('\n');
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

async function ir(ruta, condicion) {
  await cdp('Page.navigate', { url: `${SITIO}${ruta}` });
  await hasta(condicion, ruta);
  await esperar(800);
}

// Pulsa el primer botón cuyo texto contiene el dado.
async function pulsar(texto) {
  const hecho = await evaluar(`(() => {
    const boton = [...document.querySelectorAll('button')].find((candidato) =>
      candidato.textContent.replace(/\\s+/g, ' ').includes(${JSON.stringify(texto)}));
    if (!boton) return false;
    boton.scrollIntoView({ block: 'center' });
    boton.click();
    return true;
  })()`);
  if (!hecho) throw new Error(`no hay botón con «${texto}»`);
  await esperar(400);
}

const hechas = [];

// Sin `entera`, lo que cabe en la ventana; con ella, la página de arriba abajo.
async function capturar(nombre, descripcion, { entera = false, desde = null } = {}) {
  if (desde) {
    await evaluar(
      `document.querySelector(${JSON.stringify(desde)}).scrollIntoView({ block: 'start' })`,
    );
  } else {
    await evaluar('window.scrollTo(0, 0)');
  }
  await esperar(400);
  const opciones = { format: 'png' };
  if (entera) {
    const medidas = await cdp('Page.getLayoutMetrics');
    opciones.captureBeyondViewport = true;
    opciones.clip = {
      x: 0,
      y: 0,
      width: ANCHO,
      height: Math.ceil(medidas.cssContentSize.height),
      scale: 1,
    };
  }
  const respuesta = await cdp('Page.captureScreenshot', opciones);
  const imagen = Buffer.from(respuesta.data, 'base64');
  writeFileSync(join(temporal, `${nombre}.png`), imagen);
  // El ancho y el alto de un PNG están en su cabecera, en los bytes 16 a 23.
  const ancho = imagen.readUInt32BE(16);
  const alto = imagen.readUInt32BE(20);
  hechas.push({ nombre, descripcion, ancho, alto, bytes: imagen.length });
  console.log(`  ${nombre}.png · ${ancho}×${alto}`);
}

// Analiza un titular con uno de los botones de ejemplo y devuelve el veredicto.
async function analizar(ejemplo) {
  await ir('/analizar', "!!document.querySelector('button[type=submit]')");
  await pulsar(ejemplo);
  await evaluar("document.querySelector('button[type=submit]').click()");
  await hasta(
    "[...document.querySelectorAll('button')].some((boton) => boton.textContent.includes('Nuevo análisis'))",
    `el resultado de «${ejemplo}»`,
  );
  await esperar(800);
  return evaluar("document.querySelector('.veredicto h2')?.textContent.trim() ?? ''");
}

// Abre las tarjetas de señal que estén plegadas y dice cuántas eran.
async function desplegarTarjetas() {
  const plegadas = '.tarjeta button.cabecera[aria-expanded="false"]';
  const cuantas = await evaluar(`(() => {
    const cabeceras = document.querySelectorAll(${JSON.stringify(plegadas)});
    cabeceras.forEach((cabecera) => cabecera.click());
    return cabeceras.length;
  })()`);
  await hasta(
    `document.querySelectorAll(${JSON.stringify(plegadas)}).length === 0`,
    'todas las tarjetas abiertas',
  );
  await esperar(600);
  return cuantas;
}

async function recorrerPantallas() {
  await ir('/analizar', "!!document.querySelector('button[type=submit]')");
  await capturar(
    '01-formulario',
    'La pantalla de análisis (`/analizar`) antes de analizar: el formulario y los cuatro titulares de ejemplo.',
  );

  let veredicto = await analizar('clickbait claro');
  await capturar(
    '02-clickbait',
    `El resultado del ejemplo «clickbait claro», tal como se abre: lo que cabe sin desplazar. Veredicto: «${veredicto}».`,
  );
  await desplegarTarjetas();
  await capturar(
    '03-clickbait-entero',
    'El mismo resultado, la página entera, con todas las tarjetas de señal abiertas.',
    { entera: true },
  );

  veredicto = await analizar('caso ambiguo');
  await desplegarTarjetas();
  await capturar(
    '04-ambiguo-entero',
    `El resultado del ejemplo «caso ambiguo», la página entera, con todas las tarjetas abiertas. Veredicto: «${veredicto}».`,
    { entera: true },
  );

  veredicto = await analizar('en español');
  await desplegarTarjetas();
  await capturar(
    '05-espanol-entero',
    `El resultado del ejemplo «en español», la página entera, con todas las tarjetas abiertas. Veredicto: «${veredicto}».`,
    { entera: true },
  );

  await evaluar("document.querySelector('.salud .pastilla').click()");
  await hasta("document.body.innerText.includes('Comprobado a las')", 'la salud');
  await esperar(500);
  await capturar(
    '06-salud',
    'El indicador de salud de la cabecera, desplegado: las APIs externas que se sondean y su estado.',
  );

  await ir('/historial', "document.querySelectorAll('tbody tr').length > 0");
  await capturar(
    '07-historial',
    'El historial (`/historial`): las entradas más recientes, de análisis y de ejecuciones sueltas.',
  );

  await ir('/sistema', "document.querySelectorAll('.tool').length > 0");
  await capturar(
    '08-sistema',
    'Sistema (`/sistema`): el servidor MCP conectado y el principio del catálogo de herramientas.',
  );
  await pulsar('analyze_sentiment');
  await hasta(
    "!!document.querySelector('app-esquema-form textarea, app-esquema-form input')",
    'el formulario de la herramienta',
  );
  await evaluar(`(() => {
    const campo = document.querySelector('app-esquema-form textarea, app-esquema-form input');
    const prototipo = Object.getPrototypeOf(campo);
    Object.getOwnPropertyDescriptor(prototipo, 'value').set.call(campo, ${JSON.stringify(TITULAR_SISTEMA)});
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('app-esquema-form button[type=submit]').click();
  })()`);
  await hasta(
    "[...document.querySelectorAll('.tool')].some((tarjeta) => tarjeta.innerText.includes('success') || tarjeta.innerText.includes('label'))",
    'la ejecución',
  );
  await esperar(800);
  await capturar(
    '09-sistema-ejecucion',
    `Una ejecución suelta desde Sistema: \`analyze_sentiment\` con «${TITULAR_SISTEMA}», el formulario que sale de su esquema y la respuesta.`,
    { desde: '.tool:has(button[aria-expanded=true])' },
  );

  await ir('/asistente', 'document.body.innerText.length > 200');
  await esperar(1500);
  const apagado = await evaluar("document.body.innerText.includes('no se puede usar')");
  await capturar(
    apagado ? '10-asistente-apagado' : '10-asistente',
    apagado
      ? 'El asistente (`/asistente`) sin el modelo en marcha (sin sesión de GPU): explica por qué no se puede usar, en vez de ofrecer un chat que fallaría.'
      : 'El asistente (`/asistente`) con el modelo en marcha, antes de preguntar nada.',
  );
}

// Manda una pregunta y espera a que el turno acabe, con respuesta o sin ella.
async function preguntar(pregunta, conversacion, numero) {
  const antes = await evaluar("document.querySelectorAll('li.intercambio').length");
  await evaluar(`(() => {
    const campo = document.querySelector('#mensaje');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(campo, ${JSON.stringify(pregunta)});
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('form button[type=submit]').click();
  })()`);
  const inicio = new Date();
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
    `la respuesta ${numero} de la conversación ${conversacion}`,
    TOPE_TURNO,
  );
  const segundos = ((Date.now() - inicio.getTime()) / 1000).toFixed(0);
  const turno = await evaluar(`(() => {
    const ultimo = [...document.querySelectorAll('li.intercambio')].at(-1);
    const consultas = [...ultimo.querySelectorAll('.paso--modelo code')].map((codigo) => codigo.textContent.trim());
    const fallo = ultimo.querySelector('.error');
    let final = 'sin respuesta escrita';
    if (fallo) final = 'falló: ' + fallo.textContent.trim();
    else if (ultimo.querySelector('.narracion')) {
      final = consultas.length ? 'respondió' : 'respondió sin herramientas';
    }
    return { consultas, final };
  })()`);
  console.log(
    `  conversación ${conversacion} · turno ${numero}: ${segundos} s desde el navegador · ` +
      `${turno.consultas.join(' → ') || 'ninguna herramienta'} · ${turno.final}`,
  );
  return turno;
}

async function recorrerAsistente() {
  await ir('/asistente', "!!document.querySelector('#mensaje')");
  const inicio = new Date();
  let turnos = [];
  for (const conversacion of [1, 2]) {
    if (conversacion === 2) {
      await pulsar('Empezar una conversación nueva');
      await hasta("document.querySelectorAll('li.intercambio').length === 0", 'la conversación nueva');
    }
    turnos = [];
    for (const [posicion, pregunta] of preguntas.entries()) {
      turnos.push(await preguntar(pregunta, conversacion, posicion + 1));
    }
  }
  const fin = new Date();
  const marca = (fecha) => fecha.toISOString().slice(0, 19) + 'Z';
  console.log(
    `intervalo para spikes/chat_registro.sh: ${marca(new Date(inicio.getTime() - 5000))} ` +
      `${marca(new Date(fin.getTime() + 5000))}`,
  );

  const resumen = turnos
    .map(
      ({ consultas, final }, posicion) =>
        `${posicion + 1}, ${consultas.map((consulta) => `\`${consulta}\``).join(' y ') || 'ninguna herramienta'} (${final})`,
    )
    .join('; ');
  await capturar(
    '11-asistente-conversacion',
    `La segunda conversación del paso 6 de \`docs/demostracion.md\`, ya en caliente, tal como queda: las tres preguntas, lo que consultó el asistente en cada turno y su respuesta. Turnos: ${resumen}.`,
    { entera: true },
  );
  const abiertas = await desplegarTarjetas();
  if (abiertas) {
    await capturar(
      '12-asistente-conversacion-tarjetas',
      `La misma conversación, con las ${abiertas} tarjetas de señal que estaban plegadas abiertas.`,
      { entera: true },
    );
  } else {
    console.log('  no había tarjetas plegadas: la captura 12 sería igual que la 11');
  }
}

// El índice sale de las listas de todos los recorridos que haya en la carpeta.
function indice() {
  const partes = [
    '# Capturas de la versión servida',
    '',
    '*No se edita a mano: lo escribe `spikes/capturas.mjs` (#215) junto con las',
    'imágenes y la lista de cada recorrido (`<recorrido>.json`). La orden para',
    'repetirlas está en su cabecera.*',
    '',
    `Sitio: ${SITIO}. Ventana: ${ANCHO}×${ALTO} píxeles CSS a escala ${ESCALA}, tema claro, \`es-ES\`.`,
  ];
  for (const [nombre, { titulo, deja }] of Object.entries(RECORRIDOS)) {
    const fichero = join(DESTINO, `${nombre}.json`);
    if (!existsSync(fichero)) continue;
    const lista = JSON.parse(readFileSync(fichero, 'utf8'));
    partes.push(
      '',
      `## ${titulo} (\`${nombre}\`)`,
      '',
      '| Condición | Valor |',
      '|---|---|',
      `| Fecha | ${lista.fecha}, hora de Madrid |`,
      `| Commit servido | \`${lista.commit.slice(0, 7)}\`, el del clon de la máquina 1 (${lista.cambios} ficheros cambiados en él) |`,
      `| Versión del contrato | ${lista.contrato} |`,
      `| Navegador | ${lista.navegador}, sin ventana |`,
    );
    if (lista.modelo) {
      partes.push(`| Modelo | \`${lista.modelo}\`, con el prompt \`${lista.prompt}\` (de \`/api/agent\`) |`);
    }
    partes.push('', '| Fichero | Qué enseña | Píxeles | Tamaño |', '|---|---|---|---|');
    for (const { nombre: imagen, descripcion, ancho, alto, bytes } of lista.capturas) {
      partes.push(
        `| [\`${imagen}.png\`](${imagen}.png) | ${descripcion} | ${ancho}×${alto} | ${Math.round(bytes / 1024)} KB |`,
      );
    }
    partes.push(
      '',
      `${deja} De una ejecución a otra cambian, aunque el código sea el mismo, las horas, el estado de las APIs externas y lo que haya en el historial.`,
    );
  }
  return partes.join('\n') + '\n';
}

// Deja las capturas de este recorrido y borra las que su lista anterior tenía
// y ésta ya no: las de los demás recorridos no se tocan.
function guardar(navegadorUsado) {
  mkdirSync(DESTINO, { recursive: true });
  const fichero = join(DESTINO, `${recorrido}.json`);
  const nuevas = new Set(hechas.map(({ nombre }) => nombre));
  if (existsSync(fichero)) {
    for (const { nombre } of JSON.parse(readFileSync(fichero, 'utf8')).capturas) {
      if (!nuevas.has(nombre)) rmSync(join(DESTINO, `${nombre}.png`), { force: true });
    }
  }
  for (const nombre of nuevas) {
    copyFileSync(join(temporal, `${nombre}.png`), join(DESTINO, `${nombre}.png`));
  }
  const lista = {
    recorrido,
    fecha: new Date().toLocaleString('sv-SE', { timeZone: 'Europe/Madrid' }).slice(0, 16),
    commit: clon.commit,
    cambios: clon.cambios,
    contrato: contrato.info.version,
    navegador: navegadorUsado,
    ...(agente ? { modelo: agente.availability.model, prompt: agente.prompt.name } : {}),
    capturas: hechas,
  };
  writeFileSync(fichero, JSON.stringify(lista, null, 2) + '\n');
  writeFileSync(join(DESTINO, 'README.md'), indice());
}

try {
  await cdp('Page.enable');
  await cdp('Runtime.enable');
  await cdp('Emulation.setDeviceMetricsOverride', {
    width: ANCHO,
    height: ALTO,
    deviceScaleFactor: ESCALA,
    mobile: false,
  });
  await cdp('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-color-scheme', value: 'light' }],
  });
  const { product: navegadorUsado } = await cdp('Browser.getVersion');
  console.log(
    `${recorrido} · ${navegadorUsado} · ${ANCHO}×${ALTO} a escala ${ESCALA} · la máquina 1 sirve ` +
      `${clon.commit.slice(0, 7)} · contrato ${contrato.info.version}` +
      (agente ? ` · ${agente.availability.model} con ${agente.prompt.name}` : ''),
  );
  if (recorrido === 'asistente') await recorrerAsistente();
  else await recorrerPantallas();
  guardar(navegadorUsado);
  console.log(`${hechas.length} capturas de «${recorrido}» y el índice, en ${DESTINO}`);
} catch (error) {
  console.error(`No se dejó nada en ${DESTINO}: ${error.message}`);
  process.exitCode = 1;
} finally {
  // Si el navegador se cierra antes de contestar, la respuesta no llega nunca.
  await Promise.race([cdp('Browser.close').catch(() => {}), esperar(2000)]);
  conexion.close();
  await Promise.race([cerrado, esperar(5000)]);
  navegador.kill();
  for (const carpeta of [perfil, temporal]) {
    try {
      rmSync(carpeta, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
    } catch (error) {
      console.error(`No pude borrar ${carpeta}: ${error.message}`);
    }
  }
}
