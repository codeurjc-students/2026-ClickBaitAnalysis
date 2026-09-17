# Dos etapas: la primera compila el Angular con Node y la segunda lo sirve con
# Caddy. Sólo la ÚLTIMA etapa se convierte en la imagen, así que Node y
# node_modules nunca llegan a ella: no se quitan, nunca estuvieron.
#
# Etiquetas móviles (`22-slim`, `2-alpine`) hasta medir qué versión se descarga
# al construir; después se fijan a lo medido, como torch en el backend.

# 1 · Compilar. Debian slim y no alpine: esta etapa se tira, su tamaño no llega
#     a la imagen, y así compila con la misma libc que el entorno de desarrollo.
FROM node:22-slim AS compilacion

WORKDIR /frontend

# Dependencias antes que el código, porque cambian mucho menos: tocar un
# componente reutiliza esta capa y sólo repite la compilación.
#
# `npm ci` y no `npm install`: instala exactamente el lockfile y falla si no
# coincide con package.json. Ojo: NO poner `NODE_ENV=production` en esta etapa,
# o `npm ci` omite las devDependencies, que es donde está el compilador.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# La configuración por defecto de `ng build` es `production` (angular.json).
COPY frontend/ ./
RUN npm run build

# 2 · Servir. Alpine sí: Caddy es un único ejecutable de Go sin dependencias del
#     sistema, a diferencia de torch en el backend. `CMD` y `EXPOSE` se heredan
#     de la imagen base: arranca con /etc/caddy/Caddyfile y expone 80 y 443.
FROM caddy:2-alpine

COPY docker/Caddyfile /etc/caddy/Caddyfile

# `browser/` y no `dist/clickbait-web/`: COPY de un directorio copia su
# CONTENIDO, e index.html tiene que quedar en /srv, donde lo busca el Caddyfile.
COPY --from=compilacion /frontend/dist/clickbait-web/browser /srv
