"""Tests del descubrimiento automático de integraciones.

El test central es `test_un_paquete_nuevo_aparece_sin_tocar_main`: crea una
integración de mentira en un directorio temporal y comprueba que aparece sola.

El truco para no ensuciar el repositorio es extender `__path__` del paquete
`backend.integrations`: Python usa esa lista para localizar submódulos, así que
añadirle un directorio temporal hace que el import funcione de verdad, sin
copiar ficheros dentro del proyecto.
"""

import asyncio
import sys

import pytest
from mcp.server.fastmcp import FastMCP

from backend import integrations
from backend.integrations import discovery

INTEGRACIONES_REALES = ("guardian", "nlp", "nyt", "weather")

_TOOL_OK = """
def register(mcp):
    @mcp.tool()
    async def tool_de_prueba(texto: str) -> str:
        '''Una tool de prueba.'''
        return texto
"""

_TOOL_QUE_REVIENTA = """
def register(mcp):
    raise RuntimeError("esta integración está rota")
"""

_SIN_REGISTER = """
CONSTANTE = 1
"""


@pytest.fixture
def integracion_falsa(tmp_path, monkeypatch):
    """Crea un paquete de integración temporal y lo hace descubrible."""
    creados: list[str] = []

    def crear(nombre: str, cuerpo: str = _TOOL_OK):
        paquete = tmp_path / nombre
        paquete.mkdir()
        (paquete / "__init__.py").write_text("", encoding="utf-8")
        (paquete / "tool.py").write_text(cuerpo, encoding="utf-8")
        creados.append(nombre)
        # `__path__` es la lista donde Python busca submódulos del paquete:
        # ampliarla hace que `backend.integrations.<nombre>` sea importable.
        monkeypatch.setattr(
            integrations, "__path__", [*integrations.__path__, str(tmp_path)]
        )
        return nombre

    yield crear

    # Los módulos importados quedan cacheados en sys.modules y contaminarían
    # otros tests, así que se retiran.
    for nombre in creados:
        for clave in list(sys.modules):
            if clave.startswith(f"backend.integrations.{nombre}"):
                del sys.modules[clave]


def test_descubre_las_integraciones_reales():
    resultado = discovery.discover_and_register(FastMCP("test"))

    assert resultado.registered == INTEGRACIONES_REALES
    assert not resultado.failed
    assert not resultado.degraded


def test_el_orden_es_determinista():
    # El catálogo y varios tests dependen de él; el orden del sistema de
    # ficheros no está garantizado, así que se ordena explícitamente.
    primero = discovery.discover_and_register(FastMCP("a")).registered
    segundo = discovery.discover_and_register(FastMCP("b")).registered

    assert primero == segundo == tuple(sorted(primero))


def test_registra_de_verdad_las_tools():
    mcp = FastMCP("test")
    discovery.discover_and_register(mcp)

    nombres = {t.name for t in asyncio.run(mcp.list_tools())}
    # Una de cada integración, para comprobar que no se queda a medias.
    assert nombres >= {
        "get_guardian_news",
        "get_nyt_news",
        "get_forecast",
        "detect_clickbait_lexical",
    }


def test_health_no_es_una_integracion():
    resultado = discovery.discover_and_register(FastMCP("test"))

    assert "health" not in resultado.registered


# ----- Añadir una integración sin tocar código existente -----


def test_un_paquete_nuevo_aparece_sin_tocar_main(integracion_falsa):
    integracion_falsa("integracion_nueva")
    mcp = FastMCP("test")

    resultado = discovery.discover_and_register(mcp)

    assert "integracion_nueva" in resultado.registered
    nombres = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "tool_de_prueba" in nombres
    # Y las de siempre siguen ahí.
    assert set(INTEGRACIONES_REALES) <= set(resultado.registered)


# ----- Aislamiento de fallos -----


def test_una_integracion_que_revienta_no_tumba_a_las_demas(integracion_falsa):
    integracion_falsa("integracion_rota", _TOOL_QUE_REVIENTA)

    resultado = discovery.discover_and_register(FastMCP("test"))

    assert "integracion_rota" in resultado.failed
    assert "RuntimeError" in resultado.failed["integracion_rota"]
    assert resultado.degraded
    # Las otras cuatro se registran igualmente. Un paquete roto
    # no puede dejar al sistema sin las herramientas restantes.
    assert set(INTEGRACIONES_REALES) <= set(resultado.registered)


def test_un_paquete_sin_register_se_omite_sin_romper(integracion_falsa):
    integracion_falsa("paquete_de_apoyo", _SIN_REGISTER)

    resultado = discovery.discover_and_register(FastMCP("test"))

    assert "paquete_de_apoyo" in resultado.failed
    assert "paquete_de_apoyo" not in resultado.registered
    assert set(INTEGRACIONES_REALES) <= set(resultado.registered)
