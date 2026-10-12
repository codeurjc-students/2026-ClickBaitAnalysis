"""¿Qué carpetas del cliente importan de cuáles, y lo cubre el diagrama de §8?

Lo mismo que `imports_entre_capas.py` hace con el backend y §7, para el
diagrama de capas del cliente de `docs/arquitectura.md` (§8, #251): recorre los
`.ts` de `frontend/src/app/`, saca sus imports relativos —también los
`import('./…')` perezosos de las rutas—, los agrupa por carpeta de origen y de
destino, y comprueba que cada par queda cubierto por algún camino de las
flechas dibujadas. Las flechas son la dirección permitida, no cada import
concreto: basta con que exista un camino.

TypeScript no se puede leer con `ast`, así que va con una expresión regular
sobre `from '…'` e `import('…')`. Sirve porque el cliente sólo usa esas dos
formas con rutas relativas; un import de un paquete (`@angular/…`) no es de
ninguna carpeta y se ignora. Los `.spec.ts` se dejan fuera: son pruebas, no la
arquitectura.

Además lista las flechas dibujadas que ningún import forma directamente: no es
un error —un camino puede pasar por ellas—, pero una flecha así se mira dos
veces.

    .venv/bin/python spikes/imports_cliente.py
    .venv/bin/python spikes/imports_cliente.py --raiz /tmp/arbol   # otro árbol

Sale con código 1 si algún import no queda cubierto por el dibujo.

Resultado el 12 oct 2026, sobre `e9880ab` (`v0.8.0` más documentación): 16
pares de carpetas, todos con camino en el dibujo, y ninguna flecha dibujada
sin un import que la forme. Ninguna pantalla importa de otra. Con un import de
`historial/` añadido a `sistema/` en una copia, sale con código 1 y lo nombra.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# La raíz de `app/` es la cáscara: el componente con la cabecera, las rutas y la
# configuración.
CASCARA = "cáscara"
PANTALLAS = ("analisis", "asistente", "historial", "sistema")

# Las flechas del diagrama de capas del cliente de §8.
DIBUJO: dict[str, set[str]] = {
    CASCARA: {*PANTALLAS, "salud", "api"},
    **{pantalla: {"senales", "api"} for pantalla in PANTALLAS},
    "senales": {"api"},
    "salud": {"api"},
    "api": set(),
}

IMPORT_RELATIVO = re.compile(
    r"""(?:from\s+|import\s*\(\s*)['"](\.{1,2}/[^'"]+)['"]"""
)


def carpeta(fichero: Path, app: Path) -> str:
    """La carpeta de `app/` a la que pertenece un fichero, o la cáscara."""
    partes = fichero.relative_to(app).parts
    return partes[0] if len(partes) > 1 else CASCARA


def imports_entre_carpetas(raiz: Path) -> dict[tuple[str, str], list[str]]:
    """Cada par (origen, destino) de carpetas distintas, con los imports que lo forman."""
    app = raiz / "frontend" / "src" / "app"
    pares: dict[tuple[str, str], list[str]] = defaultdict(list)
    for fichero in sorted(app.rglob("*.ts")):
        if fichero.name.endswith(".spec.ts"):
            continue
        origen = carpeta(fichero, app)
        for ruta in IMPORT_RELATIVO.findall(fichero.read_text(encoding="utf-8")):
            importado = (fichero.parent / ruta).resolve()
            destino = carpeta(importado, app.resolve())
            if destino != origen:
                pares[(origen, destino)].append(f"{fichero.relative_to(app)} -> {ruta}")
    return pares


def hay_camino(origen: str, destino: str) -> bool:
    """Si las flechas del dibujo llevan de una carpeta a la otra."""
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
        "--raiz", type=Path, default=Path("."), help="carpeta que contiene frontend/"
    )
    raiz = argumentos.parse_args().raiz

    pares = imports_entre_carpetas(raiz)
    sin_cubrir = []
    for (origen, destino), ejemplos in sorted(pares.items()):
        cubierto = hay_camino(origen, destino)
        if not cubierto:
            sin_cubrir.append((origen, destino))
        marca = "ok " if cubierto else "NO "
        print(
            f"{marca} {origen:10} -> {destino:10} {len(ejemplos):3}"
            f"  p. ej. {ejemplos[0]}"
        )

    sin_import = sorted(
        (origen, destino)
        for origen, destinos in DIBUJO.items()
        for destino in destinos
        if (origen, destino) not in pares
    )
    entre_pantallas = [
        par for par in pares if par[0] in PANTALLAS and par[1] in PANTALLAS
    ]

    print(f"\n{len(pares)} pares de carpetas; sin camino en el dibujo: {len(sin_cubrir)}")
    for origen, destino in sin_cubrir:
        print(f"  {origen} -> {destino}")
    print(f"flechas dibujadas sin un import que las forme: {len(sin_import)}")
    for origen, destino in sin_import:
        print(f"  {origen} -> {destino}")
    print(f"imports entre pantallas: {len(entre_pantallas)}")
    return 1 if sin_cubrir else 0


if __name__ == "__main__":
    sys.exit(main())
