/**
 * Prefijo de la API. NO es la dirección del backend, y esa es la gracia.
 *
 * En desarrollo `proxy.conf.json` reenvía `/api/*` a `http://127.0.0.1:8000`
 * quitando el prefijo; en despliegue lo hará nginx (decisión tomada para H4).
 * Para el navegador todo sale del MISMO origen, así que no hay CORS ni
 * preflight, y la SPA no tiene que saber dónde vive la API en cada entorno.
 *
 * Vive suelto desde que hay dos servicios (#128): repetido en cada uno, cambiar
 * el prefijo obligaría a acertar en todos, y el que se olvidara seguiría
 * compilando.
 */
export const API = '/api';
