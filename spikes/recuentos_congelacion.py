"""#215 (2026-11-21) - Los recuentos de la versión congelada, para el capítulo 4.

Las notas `\\alumno` de 4.6 y 4.7 piden, de la versión congelada, el número de
pruebas del servidor y del cliente, la cobertura, el tamaño del código por
lenguaje separando lo generado, y el número de commits, ramas, pull requests e
issues. Este guion los cuenta todos con una regla escrita, para que se puedan
repetir y no salgan de contar a mano:

- **Pruebas**: las que recoge pytest (todas y sin las `integration`, que el CI
  no ejecuta) y las que ejecuta `ng test`. Se ejecutan en la copia, así que el
  guion se para si `backend/`, `tests/` o `frontend/src/` difieren del commit
  que se cuenta.
- **Cobertura**: la del CI, de ramas, con `.coveragerc` (#138), sobre
  `pytest -m "not integration"`.
- **Líneas**: de los ficheros versionados en ese commit (`git archive`), sin
  contar las vacías. Lo generado va aparte: `schema.d.ts` y `openapi.json`
  salen del contrato, y `requirements.txt` y `package-lock.json` son
  lockfiles. Los datos (`data/`) no son código.
- **El repositorio**: commits hasta ese commit (con y sin merges), y de GitHub,
  en el momento de ejecutar el guion, las pull requests (por estado y por rama
  de destino), las ramas de las que salieron, las ramas que quedan y las
  issues. GitHub cuenta lo de ahora, no lo del commit: se imprime la fecha.

Ejecutar desde la raíz, en WSL (necesita `gh` y el Node de nvm):
    .venv/bin/python spikes/recuentos_congelacion.py [commit]
"""

import json
import os
import re
import subprocess
import sys
import tarfile
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
NODE = Path.home() / ".nvm/versions/node/v22.23.2/bin"
REPOSITORIO = "codeurjc-students/2026-ClickBaitAnalysis"

# Lo que se ejecuta en la copia tiene que ser lo del commit que se cuenta.
EJECUTADO = ("backend", "tests", "frontend/src")

GENERADO = {
    "frontend/src/app/api/schema.d.ts": "tipos generados del contrato",
    "frontend/openapi.json": "el contrato, exportado",
    "requirements.txt": "lockfile de Python",
    "frontend/package-lock.json": "lockfile de npm",
}

# Lo que cuenta como código en el total de lo servido. En `backend` hay además
# dos JSON que no se escriben a mano (los pesos entrenados del lineal y la
# grabación de #265, que escribió el modelo) y Markdown (los prompts y una
# atribución): salen en la tabla, pero no en el total.
CODIGO = {"Python", "TypeScript", "HTML", "SCSS"}

LENGUAJES = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".html": "HTML",
    ".scss": "SCSS",
    ".css": "CSS",
    ".sh": "Bash",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".tex": "LaTeX",
}


def ejecutar(*orden: str, entorno: dict | None = None) -> str:
    """La salida de una orden, o se para con su error."""
    resultado = subprocess.run(
        orden, cwd=RAIZ, capture_output=True, text=True, env=entorno, check=False
    )
    if resultado.returncode not in (0, 1) and not resultado.stdout:
        raise SystemExit(f"falló {' '.join(orden)}: {resultado.stderr.strip()}")
    return resultado.stdout + resultado.stderr


def zona(ruta: str) -> str:
    """Dónde vive un fichero, para separar lo servido de lo demás."""
    if ruta.startswith("backend/evaluation/"):
        return "backend/evaluation (no se sirve)"
    if ruta.startswith("backend/"):
        return "backend (servido)"
    if ruta.startswith("frontend/src/") and ruta.endswith(".spec.ts"):
        return "frontend (pruebas)"
    if ruta.startswith("frontend/src/"):
        return "frontend (servido)"
    for carpeta in ("tests", "spikes", "docs", "docker", "despliegue", ".github"):
        if ruta.startswith(f"{carpeta}/"):
            return carpeta
    return "raíz y configuración"


def lineas(commit: str) -> None:
    """Líneas no vacías por lenguaje y zona, de los ficheros de ese commit."""
    archivo = subprocess.run(
        ["git", "archive", "--format=tar", commit],
        cwd=RAIZ,
        capture_output=True,
        check=True,
    ).stdout
    por_lenguaje: Counter[tuple[str, str]] = Counter()
    generado: dict[str, int] = {}
    ficheros: Counter[tuple[str, str]] = Counter()
    with tarfile.open(fileobj=BytesIO(archivo)) as paquete:
        for miembro in paquete.getmembers():
            if not miembro.isfile() or miembro.name.startswith("data/"):
                continue
            extension = Path(miembro.name).suffix
            contenido = paquete.extractfile(miembro)
            if contenido is None:
                continue
            texto = contenido.read().decode("utf-8", errors="replace")
            no_vacias = sum(1 for linea in texto.splitlines() if linea.strip())
            if miembro.name in GENERADO:
                generado[miembro.name] = no_vacias
                continue
            lenguaje = LENGUAJES.get(extension)
            if lenguaje is None:
                continue
            clave = (zona(miembro.name), lenguaje)
            por_lenguaje[clave] += no_vacias
            ficheros[clave] += 1

    print("\n== Líneas no vacías, por zona y lenguaje (ficheros versionados)")
    print("| Zona | Lenguaje | Ficheros | Líneas |")
    print("|---|---|---|---|")
    for (lugar, lenguaje), total in sorted(por_lenguaje.items()):
        print(f"| {lugar} | {lenguaje} | {ficheros[(lugar, lenguaje)]} | {total} |")
    servido = sum(
        total
        for (lugar, lenguaje), total in por_lenguaje.items()
        if "(servido)" in lugar and lenguaje in CODIGO
    )
    print(
        f"\nlo servido, en código ({', '.join(sorted(CODIGO))}; backend y "
        f"frontend, sin pruebas): {servido} líneas"
    )
    print("\n== Generado o lockfile, aparte")
    for ruta, total in sorted(generado.items()):
        print(f"  {ruta}: {total} líneas ({GENERADO[ruta]})")


def pruebas() -> None:
    """Las pruebas del servidor (recogidas) y del cliente (ejecutadas)."""
    print("\n== Pruebas")
    recogidas = ejecutar(".venv/bin/python", "-m", "pytest", "--collect-only", "-q")
    total = re.search(r"(\d+) tests? collected", recogidas)
    print(f"  servidor, todas: {total.group(1) if total else recogidas[-200:]}")
    sin_integracion = ejecutar(
        ".venv/bin/python",
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-m",
        "not integration",
    )
    filtradas = re.search(
        r"(\d+)/(\d+) tests? collected \((\d+) deselected\)", sin_integracion
    )
    if filtradas:
        print(
            f"  servidor, sin `integration` (las del CI): {filtradas.group(1)} "
            f"({filtradas.group(3)} de integración, que tocan la red)"
        )
    entorno = {**os.environ, "PATH": f"{NODE}:{os.environ['PATH']}"}
    cliente = subprocess.run(
        ["npx", "ng", "test", "--watch=false"],
        cwd=RAIZ / "frontend",
        capture_output=True,
        text=True,
        env=entorno,
        check=False,
    ).stdout
    sin_color = re.sub(r"\x1b\[[0-9;]*m", "", cliente)
    ficheros = re.search(r"Test Files\s+(\d+) passed", sin_color)
    casos = re.search(r"Tests\s+(\d+) passed", sin_color)
    print(
        f"  cliente: {casos.group(1) if casos else '?'} en "
        f"{ficheros.group(1) if ficheros else '?'} ficheros (`ng test`)"
    )


def cobertura() -> None:
    """La del CI: de ramas, con `.coveragerc`, sin las de integración."""
    salida = ejecutar(
        ".venv/bin/python",
        "-m",
        "pytest",
        "-q",
        "-m",
        "not integration",
        "--cov",
        "--cov-report=term",
    )
    total = re.search(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+%)", salida, re.M)
    pasadas = re.search(r"(\d+) passed", salida)
    print("\n== Cobertura del servidor (de ramas, `.coveragerc`)")
    if total:
        sentencias, sin_cubrir, ramas, ramas_a_medias, porcentaje = total.groups()
        print(
            f"  {porcentaje}: {sentencias} sentencias ({sin_cubrir} sin cubrir) y "
            f"{ramas} ramas ({ramas_a_medias} a medias), con "
            f"{pasadas.group(1) if pasadas else '?'} pruebas"
        )
    else:
        print(salida[-600:])


def gh_json(*orden: str) -> list[dict]:
    return json.loads(ejecutar("gh", *orden))


def repositorio(commit: str) -> None:
    """Commits hasta el commit; lo de GitHub, tal como está ahora."""
    print("\n== El repositorio")
    con_merges = ejecutar("git", "rev-list", "--count", commit).strip()
    sin_merges = ejecutar("git", "rev-list", "--count", "--no-merges", commit).strip()
    primero = ejecutar("git", "log", "--reverse", "--format=%as", commit).split()[0]
    print(
        f"  commits hasta {commit}: {con_merges} ({sin_merges} sin merges), desde {primero}"
    )
    print(
        f"  etiquetas: {' '.join(ejecutar('git', 'tag', '--sort=creatordate').split())}"
    )

    print(f"\n  En GitHub, a las {datetime.now().astimezone():%Y-%m-%d %H:%M %z}:")
    peticiones = gh_json(
        "pr",
        "list",
        "--repo",
        REPOSITORIO,
        "--state",
        "all",
        "--limit",
        "2000",
        "--json",
        "number,state,baseRefName,headRefName",
    )
    estados = Counter(peticion["state"] for peticion in peticiones)
    destinos = Counter(peticion["baseRefName"] for peticion in peticiones)
    ramas_de_origen = {peticion["headRefName"] for peticion in peticiones}
    print(
        f"  pull requests: {len(peticiones)} · "
        + ", ".join(
            f"{estado.lower()} {total}" for estado, total in sorted(estados.items())
        )
        + " · por destino: "
        + ", ".join(f"{rama} {total}" for rama, total in sorted(destinos.items()))
    )
    print(f"  ramas de las que salió alguna pull request: {len(ramas_de_origen)}")
    remotas = ejecutar("git", "ls-remote", "--heads", "origin").splitlines()
    print(f"  ramas que quedan en GitHub: {len(remotas)}")
    incidencias = gh_json(
        "issue",
        "list",
        "--repo",
        REPOSITORIO,
        "--state",
        "all",
        "--limit",
        "2000",
        "--json",
        "number,state",
    )
    abiertas = sum(1 for incidencia in incidencias if incidencia["state"] == "OPEN")
    print(
        f"  issues: {len(incidencias)} · abiertas {abiertas}, "
        f"cerradas {len(incidencias) - abiertas}"
    )


def main() -> None:
    commit = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    corto = ejecutar("git", "rev-parse", "--short", commit).strip()
    cambios = subprocess.run(
        ["git", "diff", "--quiet", commit, "--", *EJECUTADO], cwd=RAIZ, check=False
    ).returncode
    if cambios:
        raise SystemExit(f"{', '.join(EJECUTADO)} difieren de {corto}: no se cuenta")
    print(f"== {datetime.now().astimezone():%Y-%m-%d %H:%M %z} · el commit {corto}")
    lineas(commit)
    pruebas()
    cobertura()
    repositorio(corto)


if __name__ == "__main__":
    main()
