# Dependencias: el resumen para el triaje (2026-10-13-despues)

Generado por `spikes/vulnerabilidades_resumen.py` a partir de los JSON de esta carpeta;
las condiciones, en `condiciones.txt`. La casilla se rellena a mano: **arreglado**,
**aceptado** (con su motivo) o **no aplicable**.

## Python (pip-audit, OSV)

La gravedad es la de GitHub, del alias GHSA de cada aviso (`gravedades.json`).

- **lockfile**: 0 avisos en 0 paquetes (0 entradas en crudo)
- **fuera del lockfile**: 0 avisos en 0 paquetes (0 entradas en crudo)
- **imagen**: 8 avisos en 2 paquetes (16 entradas en crudo)
- por gravedad, todas las pasadas juntas: high 1, moderate 6, low 1

| Gravedad | Paquete | Versión | Aviso | Alias | Qué | Arreglo | Pasadas | Casilla |
|---|---|---|---|---|---|---|---|---|
| high | setuptools | 78.1.0 | PYSEC-2025-49 | BIT-setuptools-2025-47273, CVE-2025-47273, GHSA-5rjg-fvgr-3xxf | setuptools has a path traversal vulnerability in PackageIndex.download that leads to Arbi… | 78.1.1 | imagen |  |
| moderate | pip | 25.0.1 | PYSEC-2026-1795 | CVE-2025-8869, GHSA-4xh5-x5gv-qwph | pip's fallback tar extraction doesn't check symbolic links point to extraction directory | 25.3 | imagen |  |
| moderate | pip | 25.0.1 | PYSEC-2026-196 | CVE-2026-8643, GHSA-wf93-45jw-7689 | pip: Path traversal in console_scripts/gui_scripts entry point names allows installing sc… | 26.1.2 | imagen |  |
| moderate | pip | 25.0.1 | PYSEC-2026-2875 | CVE-2026-3219, GHSA-58qw-9mgm-455v | pip has an interpretation conflict due to handling both concatenated tar and ZIP files as… | 26.1 | imagen |  |
| moderate | pip | 25.0.1 | PYSEC-2026-2876 | CVE-2026-6357, GHSA-jp4c-xjxw-mgf9 | pip Vulnerable to Inclusion of Functionality from Untrusted Control Sphere | 26.1 | imagen |  |
| moderate | pip | 25.0.1 | PYSEC-2026-3721 | CVE-2026-13346, GHSA-qwm4-qh6w-59xr | pip would incorrectly handle doubly-encoded package URLs from indexes | 26.2.0 | imagen |  |
| moderate | setuptools | 78.1.0 | PYSEC-2026-3447 | BIT-setuptools-2026-59890, CVE-2026-59890, GHSA-h35f-9h28-mq5c | setuptools: MANIFEST.in exclusion bypass in sdist via Unicode normalization collision (NF… | 83.0.0 | imagen |  |
| low | pip | 25.0.1 | PYSEC-2026-1796 | CVE-2026-1703, GHSA-6vgw-5pg2-w6jp | pip Path Traversal vulnerability | 26.0 | imagen |  |

## npm (npm audit)

Versiones instaladas: de `npm_versiones.json`, guardadas por la pasada.

- **todo**: 0 avisos en 0 paquetes (0 entradas en crudo)
- **servido**: 0 avisos en 0 paquetes (0 entradas en crudo)
- por gravedad, todas las pasadas juntas: 

| Gravedad | Paquete | Versión | Aviso | Alias | Qué | Arreglo | Pasadas | Casilla |
|---|---|---|---|---|---|---|---|---|

Paquetes que sólo heredan el aviso de una dependencia suya (npm los cuenta aparte):

