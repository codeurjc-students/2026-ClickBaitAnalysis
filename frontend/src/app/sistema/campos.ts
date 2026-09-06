/**
 * Lee el `input_schema` de una herramienta y dice qué campos pintar.
 *
 * **Es la pieza que hace que añadir una tool no toque el frontend** (R6.3, y por
 * detrás R1.9). El catálogo publica el esquema JSON CRUDO —sin aplanar, para no
 * perder mínimos, máximos ni valores por defecto— y esto lo traduce a una lista
 * de descriptores que el formulario sabe pintar.
 *
 * Vive aparte del componente y sin depender de Angular a propósito: es la parte
 * con decisiones, y así se prueba con datos y sin montar nada.
 *
 * **Lo que NO reconoce se marca `desconocido` y se enseña en crudo**, en vez de
 * omitirlo. Omitir un campo mandaría un cuerpo incompleto y el 422 llegaría sin
 * explicación posible; enseñarlo feo dice la verdad — la misma regla que el
 * `@default` de `senal-card` con las señales que no conoce.
 *
 * El subconjunto cubre lo que publican las doce tools de hoy, comprobado contra
 * los esquemas reales: ocho `string`, tres opcionales como
 * `anyOf: [string, null]`, dos `integer` con `minimum`/`maximum`/`default` y dos
 * `number`. Ni enums, ni arrays, ni objetos anidados.
 */

export type TipoDeCampo = 'texto' | 'numero' | 'booleano' | 'desconocido';

export interface Campo {
  nombre: string;
  tipo: TipoDeCampo;
  requerido: boolean;
  /** La descripción del esquema, que es la ayuda que escribió quien hizo la tool. */
  descripcion: string | null;
  /** `default` del esquema. `null` significa «sin valor inicial», no «vacío». */
  valorInicial: string | number | boolean | null;
  minimo: number | null;
  maximo: number | null;
  /** El fragmento tal cual, para poder enseñarlo cuando el tipo es desconocido. */
  crudo: unknown;
}

/** Un objeto cualquiera, para mirar dentro sin castear a una forma concreta. */
type Diccionario = Record<string, unknown>;

function esObjeto(valor: unknown): valor is Diccionario {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

/**
 * El tipo declarado, resolviendo el `anyOf` con `null` que produce FastAPI.
 *
 * Un parámetro opcional de Python (`topic: str | None = None`) no llega como
 * `type: "string"` sino como `anyOf: [{type: "string"}, {type: "null"}]`. Sin
 * resolverlo, los tres campos opcionales del catálogo saldrían como
 * desconocidos.
 */
function tipoDeclarado(definicion: Diccionario): string | null {
  if (typeof definicion['type'] === 'string') return definicion['type'];

  const alternativas = definicion['anyOf'];
  if (!Array.isArray(alternativas)) return null;

  const tipos = alternativas
    .filter(esObjeto)
    .map((alternativa) => alternativa['type'])
    .filter((tipo): tipo is string => typeof tipo === 'string' && tipo !== 'null');

  // Sólo se resuelve si queda UN tipo tras descartar el null. Una unión de
  // verdad —`str | int`— no se sabe pintar, y sale como desconocida.
  return tipos.length === 1 ? tipos[0] : null;
}

function traducir(tipo: string | null): TipoDeCampo {
  if (tipo === 'string') return 'texto';
  if (tipo === 'integer' || tipo === 'number') return 'numero';
  if (tipo === 'boolean') return 'booleano';
  return 'desconocido';
}

function numeroONulo(valor: unknown): number | null {
  return typeof valor === 'number' ? valor : null;
}

export function camposDe(esquema: unknown): Campo[] {
  if (!esObjeto(esquema)) return [];

  const propiedades = esquema['properties'];
  if (!esObjeto(propiedades)) return [];

  // `required` puede no venir: una tool sin parámetros obligatorios lo omite.
  const requeridos = Array.isArray(esquema['required'])
    ? esquema['required'].filter((nombre): nombre is string => typeof nombre === 'string')
    : [];

  return Object.entries(propiedades).map(([nombre, definicion]) => {
    if (!esObjeto(definicion)) {
      return {
        nombre,
        tipo: 'desconocido' as const,
        requerido: requeridos.includes(nombre),
        descripcion: null,
        valorInicial: null,
        minimo: null,
        maximo: null,
        crudo: definicion,
      };
    }

    const inicial = definicion['default'];

    return {
      nombre,
      tipo: traducir(tipoDeclarado(definicion)),
      requerido: requeridos.includes(nombre),
      descripcion:
        typeof definicion['description'] === 'string' ? definicion['description'] : null,
      valorInicial:
        typeof inicial === 'string' ||
        typeof inicial === 'number' ||
        typeof inicial === 'boolean'
          ? inicial
          : null,
      minimo: numeroONulo(definicion['minimum']),
      maximo: numeroONulo(definicion['maximum']),
      crudo: definicion,
    };
  });
}
