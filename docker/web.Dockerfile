# Dos etapas: la primera compila el Angular con Node y la segunda lo sirve con
# Caddy. Sólo la ÚLTIMA etapa se convierte en la imagen, así que Node y
# node_modules nunca llegan a ella: no se quitan, nunca estuvieron. Medido: la
# etapa de compilación ocupa 261 MB de contenido y la imagen final, 24 MB.
#
# Versiones fijadas, como torch en el backend: Node, la misma del entorno de
# desarrollo; Caddy, la que se explica en el paso 2.

# 1 · Compilar. Debian slim y no alpine: esta etapa se tira, su tamaño no llega
#     a la imagen, y así compila con la misma libc que el entorno de desarrollo.
FROM node:22.23.2-slim AS compilacion

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
#     de la imagen base: arranca con /etc/caddy/Caddyfile y declara 80, 443
#     (TCP, y UDP para HTTP/3) y 2019, su API de administración. `EXPOSE` sólo
#     documenta: lo que se publica lo decide `-p` al arrancar.
#     Caddy es lo único expuesto a internet, así que se sube cuando trae
#     arreglos. En #260, 2.11.7 y no 2.11.4: el binario de la 2.11.4, con
#     Go 1.26.3, tenía 21 avisos altos con arreglo. En #280, 2.11.9: la 2.11.7
#     se había reconstruido sobre Alpine 3.23.7, con un crítico en brotli-libs
#     y altos en curl, y su binario (Go 1.26.8) tenía altos en la biblioteca
#     estándar, go-jose y x/net. La 2.11.9 va sobre Alpine 3.24.4 y Go 1.27.3,
#     y le queda uno de x/net/html, aceptado: el Caddyfile sólo hace
#     reverse_proxy y file_server, sin templates ni markdown.
FROM caddy:2.11.9-alpine

COPY docker/Caddyfile /etc/caddy/Caddyfile

# `browser/` y no `dist/clickbait-web/`: COPY de un directorio copia su
# CONTENIDO, e index.html tiene que quedar en /srv, donde lo busca el Caddyfile.
COPY --from=compilacion /frontend/dist/clickbait-web/browser /srv
