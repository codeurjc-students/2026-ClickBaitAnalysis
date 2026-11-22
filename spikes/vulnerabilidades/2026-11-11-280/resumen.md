# Dependencias: el resumen para el triaje (2026-11-11-280)

Generado por `spikes/vulnerabilidades_resumen.py` a partir de los JSON de esta carpeta;
las condiciones, en `condiciones.txt`. La casilla se rellena a mano: **arreglado**,
**aceptado** (con su motivo) o **no aplicable**.

## Python (pip-audit, OSV)

La gravedad es la de GitHub, del alias GHSA de cada aviso (`gravedades.json`).

- **lockfile**: 0 avisos en 0 paquetes (0 entradas en crudo)
- **fuera del lockfile**: 0 avisos en 0 paquetes (0 entradas en crudo)
- **imagen**: 1 avisos en 1 paquetes (1 entradas en crudo)
- por gravedad, todas las pasadas juntas: low 1
- **nuevos** frente a `2026-11-11-278-3.12.16`: 0 (los únicos que hay que triar)

| Gravedad | Paquete | Versión | Aviso | Alias | Qué | Arreglo | Pasadas | Nuevo | Casilla |
|---|---|---|---|---|---|---|---|---|---|
| low | setuptools | 83.0.0 | GHSA-xmj3-9gf7-h52w | — | setuptools: Windows path escape via namespace_packages.txt during legacy wheel installati… | 84.1.0 | imagen |  |  |

## npm (npm audit)

Versiones instaladas: de `npm_versiones.json`, guardadas por la pasada.

- **todo**: 3 avisos en 2 paquetes (3 entradas en crudo)
- **servido**: 0 avisos en 0 paquetes (0 entradas en crudo)
- por gravedad, todas las pasadas juntas: moderate 3
- **nuevos** frente a `2026-11-11-278-3.12.16`: 0 (los únicos que hay que triar)

| Gravedad | Paquete | Versión | Aviso | Alias | Qué | Arreglo | Pasadas | Nuevo | Casilla |
|---|---|---|---|---|---|---|---|---|---|
| moderate | @vitest/mocker | 4.1.11 | GHSA-qxg6-89mg-rqv8 | — | Vitest: Code injection via unauthenticated manual mock registration | sí, en el rango | todo |  |  |
| moderate | @vitest/mocker | 4.1.11 | GHSA-xp26-3454-mjgp | — | Vitest: Windows backslash traversal bypasses the @vitest/mocker redirect allowlist fix | sí, en el rango | todo |  |  |
| moderate | minimatch | 10.2.6 | GHSA-g3hv-75wg-m249 | — | minimatch has potential denial of service via globparts amplification | eslint@9.39.5 | todo |  |  |

Paquetes que sólo heredan el aviso de una dependencia suya (npm los cuenta aparte):

- @angular-eslint/eslint-plugin, por @angular-eslint/utils, @typescript-eslint/utils
- @angular-eslint/eslint-plugin-template, por @angular-eslint/utils, @typescript-eslint/utils
- @angular-eslint/schematics, por @angular-eslint/eslint-plugin, @angular-eslint/eslint-plugin-template
- @angular-eslint/utils, por @typescript-eslint/utils
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
