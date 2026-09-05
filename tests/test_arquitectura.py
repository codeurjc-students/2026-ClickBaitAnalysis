"""Las reglas de capas, sostenidas por un test en vez de por un comentario.

Las dos que se comprueban aquí eran ciertas y no estaban escritas en ningún
sitio, así que nada impedía romperlas. Un diagrama las ilustra pero no las
defiende: se queda desfasado en silencio, que es exactamente lo que le pasó a la
cabecera de ``docs/arquitectura.md``, afirmando durante meses que sus diagramas
eran Mermaid cuando eran SVG.

**Se parsea el árbol, no se hace grep.** Un ``# from backend.api import ...``
comentado no debe hacer fallar nada, y ``ast`` distingue código de prosa.

**Se miran también los imports dentro de funciones.** ``ast.walk`` recorre el
árbol entero, no sólo la cabecera del fichero: hay imports locales legítimos —
``orchestrator.precalentar()`` tiene uno— y el día que alguien esconda uno dentro
de una función para esquivar la regla, esto lo ve igual.

Se descartó ``import-linter``, que es la herramienta hecha para esto y expresa el
apilado entero de forma declarativa. Para dos reglas traería una dependencia más
y un paso de CI más —el job de Python instala sólo ``requirements.txt``— mientras
que esto usa la biblioteca estándar y corre en el pytest que ya existe. Si algún
día hay cinco contratos de capas, se reconsidera.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"

# Las fachadas: saben que están sirviendo a alguien. El núcleo no debe conocerlas.
FACHADAS = ("backend.api", "backend.main")

# El núcleo se define por EXCLUSIÓN: todo `backend/` menos esto.
#
# Antes se enumeraban los paquetes incluidos —`analysis`, `integrations`,
# `core`—, y eso dejaba un agujero silencioso: un paquete nuevo quedaba fuera de
# la regla sin que nadie lo notara. `backend/agent/` llega con R13 y es
# exactamente el caso, porque el agente orquesta herramientas y la tentación de
# reutilizar lo que hay en `api/` es real (#137).
#
# Con la lista invertida, un paquete nuevo entra cubierto por defecto y sacarlo
# exige editar esta línea a mano — que es la decisión consciente que se quiere
# forzar. Mismo criterio que la otra prueba de este fichero, que lista
# excepciones en vez de detectores.
FUERA_DEL_NUCLEO = {"api", "main.py"}

# Únicos módulos de la capa NLP a los que se les permite leer configuración:
# `client.py` necesita el token y el trabajo de `factory.py` ES leer settings.
#
# La lista es de EXCEPCIONES, no de detectores, y eso es deliberado: un detector
# nuevo queda cubierto sin tocar nada, y meter `settings` en un módulo nuevo
# obliga a editar esta línea a mano — que es la decisión consciente que se quiere
# forzar cuando llegue la parametrización de umbrales.
LEEN_CONFIGURACION = {"client.py", "factory.py"}

CONFIGURACION = "backend.config.settings"


def _importes(fichero: Path) -> set[str]:
    """Módulos que importa el fichero, en cualquier punto del árbol."""
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    modulos: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            modulos.add(nodo.module)
    return modulos


def _modulos_del_nucleo() -> list[Path]:
    """Todo módulo de ``backend/`` que no sea una fachada."""
    return [
        fichero
        for fichero in sorted(BACKEND.rglob("*.py"))
        if fichero.relative_to(BACKEND).parts[0] not in FUERA_DEL_NUCLEO
    ]


def test_el_nucleo_no_importa_de_las_fachadas():
    """El núcleo no sabe quién lo llama, y por eso puede tener dos fachadas.

    Si `analysis/` importara de `api/`, servir el mismo análisis por MCP dejaría
    de ser posible sin arrastrar FastAPI detrás.
    """
    modulos = _modulos_del_nucleo()

    # Sin esto, un fallo del recorrido —una ruta mal puesta, un `parts[0]` que
    # deja de casar— convertiría la prueba en un `assert not []` que pasa
    # siempre. Vigila al vigilante.
    assert modulos, "No se recorrió ningún módulo: la regla no comprueba nada."

    infracciones = [
        f"{fichero.relative_to(BACKEND)} importa {modulo}"
        for fichero in modulos
        for modulo in _importes(fichero)
        if modulo.startswith(FACHADAS)
    ]

    assert not infracciones, "El núcleo importa de las fachadas:\n" + "\n".join(
        infracciones
    )


def test_los_detectores_no_conocen_la_configuracion():
    """Los detectores son lógica pura: se prueban sin montar nada.

    En cuanto uno lea `settings`, probarlo exige un entorno con las claves
    puestas y deja de poder usarse como biblioteca suelta.
    """
    nlp = BACKEND / "integrations" / "nlp"

    infracciones = [
        f"{fichero.name} importa {CONFIGURACION}"
        for fichero in sorted(nlp.glob("*.py"))
        if fichero.name not in LEEN_CONFIGURACION
        and any(modulo.startswith(CONFIGURACION) for modulo in _importes(fichero))
    ]

    assert not infracciones, (
        "Un módulo de la capa NLP que no debería lee la configuración:\n"
        + "\n".join(infracciones)
        + "\n\nSi es deliberado, añádelo a LEEN_CONFIGURACION y explica por qué."
    )
