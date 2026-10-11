"""¿Qué capas de `backend/` importan de cuáles, y lo cubre el diagrama de §7?

Responde a la pregunta con la que se revisa el diagrama de capas de
`docs/arquitectura.md` (§7): recorre con `ast` todos los módulos de
`backend/`, incluidos los imports dentro de funciones, agrupa cada import por
la capa de origen y la de destino, y comprueba que cada par queda cubierto por
algún camino de las flechas dibujadas. Las flechas son la dirección permitida,
no cada import concreto: basta con que exista un camino.

Se escribió el 11 oct 2026, al poner el diagrama al día con `v0.8`, y repite
lo que #193 hizo a mano al cerrar H5. Con `--raiz` mide otro árbol, por
ejemplo el de un tag:

    git archive v0.6.0 backend | tar -x -C /tmp/arbol06
    .venv/bin/python spikes/imports_entre_capas.py --raiz /tmp/arbol06

Sin argumentos, mide la copia de trabajo. Sale con código 1 si algún import
no queda cubierto por el dibujo.
"""

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

# Las flechas del diagrama «Hoy, en v0.8» de §7. «Fachadas» son api/ y main.py.
FACHADAS = "fachadas"
DIBUJO: dict[str, set[str]] = {
    FACHADAS: {"analysis", "agent", "integrations/llm"},
    "analysis": {"integrations"},
    "integrations": {"core"},
    "core": {"config", "integrations"},
    "agent": {"core", "integrations/llm"},
    "integrations/llm": {"core", "config"},
    "evaluation": {"analysis"},
    "config": set(),
}


def capa(modulo: str) -> str:
    """La capa de un módulo con nombre `backend.…`, o "" si es de fuera."""
    partes = modulo.split(".")
    if partes[0] != "backend" or len(partes) < 2:
        return ""
    if partes[1] in ("api", "main"):
        return FACHADAS
    if partes[1] == "integrations" and len(partes) > 2 and partes[2] == "llm":
        return "integrations/llm"
    return partes[1]


def imports_entre_capas(raiz: Path) -> dict[tuple[str, str], list[str]]:
    """Cada par (origen, destino) de capas distintas, con los imports que lo forman."""
    pares: dict[tuple[str, str], list[str]] = defaultdict(list)
    for fichero in sorted((raiz / "backend").rglob("*.py")):
        modulo = ".".join(fichero.relative_to(raiz).with_suffix("").parts)
        origen = capa(modulo)
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                destinos = [alias.name for alias in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level:
                destinos = [nodo.module]
            else:
                continue
            for destino in destinos:
                capa_destino = capa(destino)
                if capa_destino and capa_destino != origen:
                    pares[(origen, capa_destino)].append(
                        f"{fichero.relative_to(raiz / 'backend')} -> {destino}"
                    )
    return pares


def hay_camino(origen: str, destino: str) -> bool:
    """Si las flechas del dibujo llevan de una capa a la otra."""
    pendientes, vistas = [origen], {origen}
    while pendientes:
        actual = pendientes.pop()
        for siguiente in DIBUJO.get(actual, set()):
            if siguiente == destino:
                return True
            if siguiente not in vistas:
                vistas.add(siguiente)
                pendientes.append(siguiente)
    return False


def main() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument(
        "--raiz", type=Path, default=Path("."), help="carpeta que contiene backend/"
    )
    raiz = argumentos.parse_args().raiz

    pares = imports_entre_capas(raiz)
    sin_cubrir = []
    for (origen, destino), ejemplos in sorted(pares.items()):
        cubierto = hay_camino(origen, destino)
        if not cubierto:
            sin_cubrir.append((origen, destino))
        marca = "ok " if cubierto else "NO "
        print(
            f"{marca} {origen:18} -> {destino:18} {len(ejemplos):3}"
            f"  p. ej. {ejemplos[0]}"
        )

    print(f"\n{len(pares)} pares de capas; sin camino en el dibujo: {len(sin_cubrir)}")
    for origen, destino in sin_cubrir:
        print(f"  {origen} -> {destino}")
    return 1 if sin_cubrir else 0


if __name__ == "__main__":
    sys.exit(main())
