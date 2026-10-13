"""#260 (2026-10-13) - El resumen de las pasadas de dependencias, para el triaje.

Lee la carpeta que deja `vulnerabilidades_dependencias.sh` y escribe en ella
`resumen.md`: una tabla por ecosistema, con cada aviso UNA vez por paquete y
versión, las pasadas en que aparece y la casilla del triaje vacía (arreglado,
aceptado con su motivo o no aplicable), que se rellena a mano.

Lo que no se deduce leyéndolo:

- pip-audit 2.10.1 con `-s osv` lista cada aviso dos veces (93 entradas para 50
  avisos en la primera pasada): el resumen da las dos cifras, la cruda y la
  que cuenta.
- pip-audit no da la gravedad, y los avisos PYSEC de OSV sólo traen un vector
  CVSS, sin etiqueta. La etiqueta se toma de su alias GHSA
  (`database_specific.severity`): la revisa GitHub a mano y es la misma escala
  que usa npm audit, así que las dos tablas se comparan. Un aviso sin alias
  GHSA queda «sin clasificar», con su vector.
- Las gravedades se guardan en `gravedades.json`, junto a los JSON de las
  pasadas: repetir el resumen no vuelve a la red, y la cifra no cambia aunque
  GitHub reclasifique un aviso después.
- npm audit no da la versión instalada: se lee de `frontend/package-lock.json`,
  y el resumen anota su hash de git para poder recuperarlo después de un
  `npm audit fix`.

Uso, desde la raíz (sólo biblioteca estándar):
    python3 spikes/vulnerabilidades_resumen.py spikes/vulnerabilidades/<fecha>
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LOCKFILE_NPM = RAIZ / "frontend" / "package-lock.json"
OSV = "https://api.osv.dev/v1/vulns/"

PASADAS_PIP = {
    "pip_lockfile": "lockfile",
    "pip_fuera_del_lockfile": "fuera del lockfile",
    "pip_imagen": "imagen",
}
PASADAS_NPM = {"npm_todo": "todo", "npm_servido": "servido"}

# De más a menos grave; lo que no está en la lista va al final.
ORDEN_GRAVEDAD = ["critical", "high", "moderate", "low", "sin clasificar"]


@dataclass
class Aviso:
    paquete: str
    version: str
    identificador: str
    alias: list[str]
    que: str
    arreglo: str
    gravedad: str = "sin clasificar"
    pasadas: set[str] = field(default_factory=set)


def _resumir_texto(texto: str, largo: int = 90) -> str:
    primera_linea = (texto or "").strip().splitlines()[0] if texto else ""
    primera_linea = primera_linea.replace("|", "\\|")
    return primera_linea if len(primera_linea) <= largo else primera_linea[: largo - 1] + "…"


def _consultar_osv(identificador: str) -> dict | None:
    try:
        with urllib.request.urlopen(OSV + identificador, timeout=15) as respuesta:
            return json.load(respuesta)
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"  OSV no respondió para {identificador}: {error}", file=sys.stderr)
        return None


def _gravedad_de(aviso: Aviso, gravedades: dict) -> str:
    """La etiqueta de GitHub, del alias GHSA; si no hay, «sin clasificar»."""
    if aviso.identificador in gravedades:
        return gravedades[aviso.identificador]["gravedad"]
    # El GHSA puede ser el propio aviso (pasa con alguno de cryptography) o
    # uno de sus alias (lo normal con los PYSEC).
    candidatos = [aviso.identificador, *aviso.alias]
    ghsa = next((candidato for candidato in candidatos if candidato.startswith("GHSA-")), None)
    registro = {"ghsa": ghsa, "gravedad": "sin clasificar", "cvss": None}
    principal = _consultar_osv(aviso.identificador)
    if principal is None:
        return "sin clasificar"  # sin guardar: se reintenta la próxima vez
    vectores = principal.get("severity") or []
    registro["cvss"] = vectores[0]["score"] if vectores else None
    if ghsa:
        de_github = _consultar_osv(ghsa)
        if de_github is None:
            return "sin clasificar"
        etiqueta = (de_github.get("database_specific") or {}).get("severity")
        if etiqueta:
            registro["gravedad"] = etiqueta.lower()
    gravedades[aviso.identificador] = registro
    return registro["gravedad"]


def _avisos_pip(carpeta: Path) -> tuple[dict[tuple, Aviso], Counter]:
    avisos: dict[tuple, Aviso] = {}
    entradas_crudas: Counter = Counter()
    for fichero, pasada in PASADAS_PIP.items():
        datos = json.loads((carpeta / f"{fichero}.json").read_text())
        for dependencia in datos["dependencies"]:
            for vulnerabilidad in dependencia.get("vulns") or []:
                entradas_crudas[pasada] += 1
                clave = (dependencia["name"], dependencia["version"], vulnerabilidad["id"])
                if clave not in avisos:
                    avisos[clave] = Aviso(
                        paquete=dependencia["name"],
                        version=dependencia["version"],
                        identificador=vulnerabilidad["id"],
                        alias=sorted(vulnerabilidad.get("aliases") or []),
                        que=_resumir_texto(vulnerabilidad.get("description", "")),
                        arreglo=", ".join(vulnerabilidad.get("fix_versions") or []) or "—",
                    )
                avisos[clave].pasadas.add(pasada)
    return avisos, entradas_crudas


def _versiones_npm() -> dict[str, str]:
    paquetes = json.loads(LOCKFILE_NPM.read_text())["packages"]
    return {ruta: datos.get("version", "?") for ruta, datos in paquetes.items()}


def _avisos_npm(carpeta: Path) -> tuple[dict[tuple, Aviso], dict[str, set[str]], Counter]:
    versiones = _versiones_npm()
    avisos: dict[tuple, Aviso] = {}
    arrastrados: dict[str, set[str]] = {}  # paquete -> de quién hereda el aviso
    entradas_crudas: Counter = Counter()
    for fichero, pasada in PASADAS_NPM.items():
        datos = json.loads((carpeta / f"{fichero}.json").read_text())
        for nombre, entrada in datos["vulnerabilities"].items():
            instaladas = ", ".join(sorted({versiones.get(nodo, "?") for nodo in entrada["nodes"]}))
            arreglo = entrada["fixAvailable"]
            if isinstance(arreglo, dict):
                arreglo = f"{arreglo['name']}@{arreglo['version']}"
            for origen in entrada["via"]:
                if isinstance(origen, str):
                    arrastrados.setdefault(nombre, set()).add(origen)
                    continue
                entradas_crudas[pasada] += 1
                identificador = origen["url"].rsplit("/", 1)[-1]
                clave = (nombre, instaladas, identificador)
                if clave not in avisos:
                    avisos[clave] = Aviso(
                        paquete=nombre,
                        version=instaladas,
                        identificador=identificador,
                        alias=[],
                        que=_resumir_texto(origen.get("title", "")),
                        arreglo="sí, en el rango" if arreglo is True else str(arreglo),
                        gravedad=origen.get("severity", "sin clasificar"),
                    )
                avisos[clave].pasadas.add(pasada)
    return avisos, arrastrados, entradas_crudas


def _orden(aviso: Aviso) -> tuple:
    posicion = ORDEN_GRAVEDAD.index(aviso.gravedad) if aviso.gravedad in ORDEN_GRAVEDAD else len(ORDEN_GRAVEDAD)
    return (posicion, aviso.paquete.lower(), aviso.identificador)


def _tabla(avisos: list[Aviso]) -> list[str]:
    lineas = [
        "| Gravedad | Paquete | Versión | Aviso | Alias | Qué | Arreglo | Pasadas | Casilla |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for aviso in sorted(avisos, key=_orden):
        lineas.append(
            f"| {aviso.gravedad} | {aviso.paquete} | {aviso.version} | {aviso.identificador} "
            f"| {', '.join(aviso.alias) or '—'} | {aviso.que} | {aviso.arreglo} "
            f"| {', '.join(sorted(aviso.pasadas))} |  |"
        )
    return lineas


def _recuento(avisos: list[Aviso], entradas_crudas: Counter, pasadas: dict[str, str]) -> list[str]:
    por_gravedad = Counter(aviso.gravedad for aviso in avisos)
    lineas = []
    for pasada in pasadas.values():
        de_la_pasada = [aviso for aviso in avisos if pasada in aviso.pasadas]
        paquetes = {aviso.paquete for aviso in de_la_pasada}
        lineas.append(
            f"- **{pasada}**: {len(de_la_pasada)} avisos en {len(paquetes)} paquetes "
            f"({entradas_crudas[pasada]} entradas en crudo)"
        )
    lineas.append(
        "- por gravedad, todas las pasadas juntas: "
        + ", ".join(f"{gravedad} {por_gravedad[gravedad]}" for gravedad in ORDEN_GRAVEDAD if por_gravedad[gravedad])
    )
    return lineas


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    carpeta = Path(sys.argv[1])
    ruta_gravedades = carpeta / "gravedades.json"
    gravedades = json.loads(ruta_gravedades.read_text()) if ruta_gravedades.exists() else {}

    avisos_pip, crudas_pip = _avisos_pip(carpeta)
    for aviso in avisos_pip.values():
        aviso.gravedad = _gravedad_de(aviso, gravedades)
    ruta_gravedades.write_text(json.dumps(gravedades, indent=1, sort_keys=True) + "\n")

    avisos_npm, arrastrados, crudas_npm = _avisos_npm(carpeta)
    hash_lockfile = subprocess.run(
        ["git", "hash-object", str(LOCKFILE_NPM)], capture_output=True, text=True, check=True
    ).stdout.strip()

    lineas = [
        f"# Dependencias: el resumen para el triaje ({carpeta.name})",
        "",
        "Generado por `spikes/vulnerabilidades_resumen.py` a partir de los JSON de esta carpeta;",
        "las condiciones, en `condiciones.txt`. La casilla se rellena a mano: **arreglado**,",
        "**aceptado** (con su motivo) o **no aplicable**.",
        "",
        "## Python (pip-audit, OSV)",
        "",
        "La gravedad es la de GitHub, del alias GHSA de cada aviso (`gravedades.json`).",
        "",
        *_recuento(list(avisos_pip.values()), crudas_pip, PASADAS_PIP),
        "",
        *_tabla(list(avisos_pip.values())),
        "",
        "## npm (npm audit)",
        "",
        f"Versiones instaladas de `frontend/package-lock.json`, blob `{hash_lockfile}`.",
        "",
        *_recuento(list(avisos_npm.values()), crudas_npm, PASADAS_NPM),
        "",
        *_tabla(list(avisos_npm.values())),
        "",
        "Paquetes que sólo heredan el aviso de una dependencia suya (npm los cuenta aparte):",
        "",
        *[f"- {paquete}, por {', '.join(sorted(origenes))}" for paquete, origenes in sorted(arrastrados.items())],
        "",
    ]
    (carpeta / "resumen.md").write_text("\n".join(lineas))
    print("\n".join(lineas[:4]))
    print(f"Escrito {carpeta / 'resumen.md'}")


if __name__ == "__main__":
    main()
