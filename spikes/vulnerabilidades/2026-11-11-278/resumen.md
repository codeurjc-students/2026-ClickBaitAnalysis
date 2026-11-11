# Dependencias: el resumen para el triaje (2026-11-11-278)

Generado por `spikes/vulnerabilidades_resumen.py` a partir de los JSON de esta carpeta;
las condiciones, en `condiciones.txt`. La casilla se rellena a mano: **arreglado**,
**aceptado** (con su motivo) o **no aplicable**.

## Python (pip-audit, OSV)

La gravedad es la de GitHub, del alias GHSA de cada aviso (`gravedades.json`).

- **lockfile**: 10 avisos en 2 paquetes (11 entradas en crudo)
- **fuera del lockfile**: 0 avisos en 0 paquetes (0 entradas en crudo)
- **imagen**: 11 avisos en 3 paquetes (12 entradas en crudo)
- por gravedad, todas las pasadas juntas: critical 1, high 1, moderate 6, low 3
- **nuevos** frente a `2026-10-13-base-arreglada`: 11 (los únicos que hay que triar)

| Gravedad | Paquete | Versión | Aviso | Alias | Qué | Arreglo | Pasadas | Nuevo | Casilla |
|---|---|---|---|---|---|---|---|---|---|
| critical | certifi | 2026.2.25 | PYSEC-2026-4320 | GHSA-6q48-6c7w-9gw2 | certifi bundles emSign root CAs with compromised intermediate CA keys | 2026.10.18 | imagen, lockfile | **sí** |  |
| high | filelock | 3.29.4 | CVE-2026-112940 | GHSA-v4x8-3wr5-3wq8 | filelock ReadWriteLock: SQLite reopens the lock database by name, so a planted symlink or… | 4.2.1 | imagen, lockfile | **sí** |  |
| moderate | filelock | 3.29.4 | CVE-2026-112909 | GHSA-69hj-f68j-2879 | filelock: UnixFileLock truncates and chmods any regular file another user renames or hard… | 4.2.1 | imagen, lockfile | **sí** |  |
| moderate | filelock | 3.29.4 | CVE-2026-112910 | GHSA-8mx5-7m5m-r77g | filelock: WindowsFileLock ignores mode: a 0o600 lock file and the ReadWriteLock database … | 4.2.1 | imagen, lockfile | **sí** |  |
| moderate | filelock | 3.29.4 | CVE-2026-112915 | GHSA-cwqr-hh33-gh44 | filelock ReadWriteLock: a crafted lock database makes every acquire stall or hang regardl… | 4.2.1 | imagen, lockfile | **sí** |  |
| moderate | filelock | 3.29.4 | CVE-2026-112935 | GHSA-fq56-3cx3-fjxp | filelock: SoftFileLock stale-lock break removes a live lock file on a reused inode number… | 4.2.1 | imagen, lockfile | **sí** |  |
| moderate | filelock | 3.29.4 | CVE-2026-112936 | GHSA-j8f7-rjxc-mr56 | filelock: ReadWriteLock follows a symlink at the lock path into SQLite | 4.0.9 | imagen, lockfile | **sí** |  |
| moderate | filelock | 3.29.4 | CVE-2026-112939 | GHSA-rfpc-qcw5-3pc4 | filelock: SoftFileLock removes a live holder's marker when another user forges the PID in… | 4.2.1 | imagen, lockfile | **sí** |  |
| low | filelock | 3.29.4 | CVE-2026-112907 | GHSA-567q-5qvw-pf92 | filelock: On Windows an oplock on a soft lock's marker holds SoftFileLock.acquire() past … | 4.2.1 | imagen, lockfile | **sí** |  |
| low | filelock | 3.29.4 | CVE-2026-112913 | GHSA-9vhv-jxww-xfm5 | filelock: ReadWriteLock on Windows acts on SQLite side files another local user places be… | 4.2.1 | imagen, lockfile | **sí** |  |
| low | setuptools | 83.0.0 | GHSA-xmj3-9gf7-h52w | — | setuptools: Windows path escape via namespace_packages.txt during legacy wheel installati… | 84.1.0 | imagen | **sí** |  |

## npm (npm audit)

Versiones instaladas: de `npm_versiones.json`, guardadas por la pasada.

- **todo**: 22 avisos en 6 paquetes (22 entradas en crudo)
- **servido**: 1 avisos en 1 paquetes (1 entradas en crudo)
- por gravedad, todas las pasadas juntas: high 6, moderate 13, low 3
- **nuevos** frente a `2026-10-13-base-arreglada`: 22 (los únicos que hay que triar)

| Gravedad | Paquete | Versión | Aviso | Alias | Qué | Arreglo | Pasadas | Nuevo | Casilla |
|---|---|---|---|---|---|---|---|---|---|
| high | undici | 7.30.0 | GHSA-2m5v-pch6-74hx | — | undici vulnerable to TLS certificate validation bypass via dropped tls options in Agent | sí, en el rango | todo | **sí** |  |
| high | undici | 7.30.0 | GHSA-4w7w-5xrc-9h26 | — | undici vulnerable to cache poisoning and cross-user disclosure via cross-origin redirects | sí, en el rango | todo | **sí** |  |
| high | undici | 7.30.0 | GHSA-qrxm-fqhp-jwvm | — | undici vulnerable to Denial of Service via TLS 1.2 certificate-changing renegotiation | sí, en el rango | todo | **sí** |  |
| high | undici | 7.30.0 | GHSA-xjj6-f33q-929c | — | undici vulnerable to Denial of Service via unhandled error on excessive content-encodings | sí, en el rango | todo | **sí** |  |
| high | vite | 8.3.0 | GHSA-587h-7wmj-h5pm | — | launch-editor: `fs.existsSync()` existence check can be bypassed on Windows | sí, en el rango | todo | **sí** |  |
| high | zod | 4.6.5 | GHSA-mrhx-c7xc-m3w5 | — | Zod can exhaust memory while validating oversized constrained collections | sí, en el rango | servido, todo | **sí** |  |
| moderate | @vitest/mocker | 4.1.11 | GHSA-qxg6-89mg-rqv8 | — | Vitest: Code injection via unauthenticated manual mock registration | sí, en el rango | todo | **sí** |  |
| moderate | @vitest/mocker | 4.1.11 | GHSA-xp26-3454-mjgp | — | Vitest: Windows backslash traversal bypasses the @vitest/mocker redirect allowlist fix | sí, en el rango | todo | **sí** |  |
| moderate | fast-uri | 3.1.8 | GHSA-w74x-v6f9-j3xg | — | fast-uri vulnerable to URI scheme spoofing via percent-encoded scheme decoding | sí, en el rango | todo | **sí** |  |
| moderate | fast-uri | 3.1.8 | GHSA-wjr9-j795-jxcr | — | fast-uri vulnerable to host confusion via unchecked WHATWG host canonicalization | sí, en el rango | todo | **sí** |  |
| moderate | minimatch | 10.2.6 | GHSA-g3hv-75wg-m249 | — | minimatch has potential denial of service via globparts amplification | eslint@9.39.5 | todo | **sí** |  |
| moderate | undici | 7.30.0 | GHSA-4qv8-2p9j-2685 | — | undici vulnerable to Denial of Service via unbounded memory in the EventSource parser | sí, en el rango | todo | **sí** |  |
| moderate | undici | 7.30.0 | GHSA-55wc-3pg8-jfw6 | — | undici vulnerable to Denial of Service via unhandled exception in the decompress intercep… | sí, en el rango | todo | **sí** |  |
| moderate | undici | 7.30.0 | GHSA-9fm3-97px-rjf6 | — | undici WebSocket client vulnerable to Denial of Service via unbounded automatic PONG buff… | sí, en el rango | todo | **sí** |  |
| moderate | undici | 7.30.0 | GHSA-f72v-6w45-q472 | — | undici vulnerable to Subresource Integrity bypass via non-lowercase algorithm tokens | sí, en el rango | todo | **sí** |  |
| moderate | vite | 8.3.0 | GHSA-698v-4r3x-3vcv | — | launch-editor: escapeCmdArgs() omits % escaping on Windows | sí, en el rango | todo | **sí** |  |
| moderate | vite | 8.3.0 | GHSA-r825-w8mm-5pxw | — | launch-editor: Editor CLI flag misinterpretation causing arbitrary command execution for … | sí, en el rango | todo | **sí** |  |
| moderate | vite | 8.3.0 | GHSA-rq7h-c2jc-7f22 | — | Vite: Files outside `server.fs.allow` could be served when project paths match system pat… | sí, en el rango | todo | **sí** |  |
| moderate | vite | 8.3.0 | GHSA-vfpm-58rq-9qcg | — | Vite: First 4 bytes of files outside of `server.fs` setting is exposed by `?vite-wasm-ins… | sí, en el rango | todo | **sí** |  |
| low | fast-uri | 3.1.8 | GHSA-333x-w4r6-6crp | — | fast-uri vulnerable to scheme injection via an unescaped first-segment colon in suffix re… | sí, en el rango | todo | **sí** |  |
| low | fast-uri | 3.1.8 | GHSA-xhq7-xmqj-769h | — | fast-uri vulnerable to improper path equivalence in relative reference normalization | sí, en el rango | todo | **sí** |  |
| low | vite | 8.3.0 | GHSA-9jrq-w75r-8gcw | — | Vite: Cross origin script execution through Vite custom middleware | sí, en el rango | todo | **sí** |  |

Paquetes que sólo heredan el aviso de una dependencia suya (npm los cuenta aparte):

- @angular-eslint/eslint-plugin, por @angular-eslint/utils, @typescript-eslint/utils
- @angular-eslint/eslint-plugin-template, por @angular-eslint/utils, @typescript-eslint/utils
- @angular-eslint/schematics, por @angular-eslint/eslint-plugin, @angular-eslint/eslint-plugin-template
- @angular-eslint/utils, por @typescript-eslint/utils
- @angular/build, por vite
- @angular/cli, por zod
- @eslint/config-array, por minimatch
- @eslint/js, por eslint
- @typescript-eslint/eslint-plugin, por @typescript-eslint/parser, @typescript-eslint/type-utils, @typescript-eslint/utils
- @typescript-eslint/parser, por @typescript-eslint/typescript-estree
- @typescript-eslint/type-utils, por @typescript-eslint/typescript-estree, @typescript-eslint/utils
- @typescript-eslint/typescript-estree, por minimatch
- @typescript-eslint/utils, por @typescript-eslint/typescript-estree
- angular-eslint, por @angular-eslint/eslint-plugin, @angular-eslint/eslint-plugin-template, @angular-eslint/schematics, @typescript-eslint/utils
- eslint, por @eslint/config-array, minimatch
- typescript-eslint, por @typescript-eslint/eslint-plugin, @typescript-eslint/parser, @typescript-eslint/typescript-estree, @typescript-eslint/utils
- vitest, por @vitest/mocker
