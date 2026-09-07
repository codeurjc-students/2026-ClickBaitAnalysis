"""Descubrir e invocar herramientas MCP, sin saber quién pregunta.

Este módulo es el mecanismo; la traducción al contrato REST vive en ``api/``.
La frontera está puesta donde deja de ser genérico: aquí se habla de servidores,
herramientas y esquemas de entrada, y no de códigos de estado ni de fichas de
modelo.

**Por qué en ``core/`` y no en ``integrations/``** (#137). El criterio de
``integrations/`` es «¿envuelve algo *externo al proyecto*?», y los servidores
MCP son nuestros; su cláusula de exclusión añade que la maquinaria que descubre
o describe las integraciones opera *sobre* ellas y no *es* una. El criterio de
``core/`` —«¿lo usa más de una capa y no sabe nada del dominio del clickbait?»—
lo cumple: lo usarán la API REST y el agente de R13, y aquí dentro no aparece un
titular ni una señal.

**El timeout entra por parámetro**, no leyendo ``settings``. Misma regla que
mantiene a los detectores NLP ignorantes de la configuración: se prueban sin
montar un entorno, y quien decide el corte es quien conoce el caso de uso — la
API tiene dos distintos, uno para descubrir y otro para ejecutar.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from jsonschema import Draft7Validator
from mcp.types import CallToolResult, TextContent, Tool

from backend.core.mcp.session import open_session
from backend.core.models import ToolResult

log = structlog.get_logger()


class ToolNotFound(Exception):
    """La herramienta no está en ningún servidor consultado."""


class InvalidArguments(Exception):
    """Los argumentos no encajan en el esquema que publica la herramienta."""


class ToolTimeout(Exception):
    """El servidor MCP no respondió dentro del corte pedido.

    Es su **propia** categoría y no un resultado fallido, porque no son lo
    mismo: un resultado fallido significa «la herramienta se ejecutó y falló», y
    aquí puede haber salido perfectamente.

    Lo que ha fallado es la espera, no el trabajo. Quien traduzca esto a HTTP
    debe distinguirlo: decir «el análisis falló» sería mentir.
    """


@dataclass(frozen=True)
class Invocation:
    """Lo que devolvió una herramienta, y qué servidor la sirvió.

    ``ToolResult`` por sí solo no basta —no lleva el servidor, y el contrato de
    ``/tools/{name}/execute`` lo publica— pero añadirle el campo lo ensuciaría
    para las cinco señales NLP, que no tienen ninguno. De ahí este envoltorio.

    Los otros tres finales posibles de una invocación no viajan aquí: son
    excepciones, porque interrumpen el flujo en vez de ser un resultado.
    """

    server: str
    result: ToolResult


@dataclass(frozen=True)
class ServerCatalog:
    """Lo que publica un servidor MCP: cómo se llama y qué herramientas trae.

    Las herramientas van como ``Tool`` del protocolo, sin traducir. Quien lo
    consuma decide qué campos necesita — la API construye su ``ToolInfo`` con
    ficha de modelo incluida, y el agente querrá el ``inputSchema`` y poco más.
    """

    url: str
    server: str
    tools: list[Tool]


async def execute_tool(
    name: str,
    arguments: dict,
    *,
    servers: Sequence[str],
    timeout: float,
) -> Invocation:
    """Localiza la herramienta, valida los argumentos y la invoca.

    **Nada se lanza desde dentro de la sesión.** La sesión MCP abre un *task
    group* de anyio, y anyio envuelve en un ``ExceptionGroup`` lo que se lance
    ahí dentro: un ``except InvalidArguments`` de quien llame no lo capturaría.
    Por eso ``_intentar`` **devuelve** lo que ha pasado y es aquí, ya fuera,
    donde se decide qué excepción sale.
    """
    for url in servers:
        try:
            intento = await _intentar(url, name, arguments, timeout)

        # `except*` y no `except`: lo que sale de la sesión viene envuelto DOS
        # veces —un task group de anyio por capa, `streamable_http_client` y
        # `ClientSession`— y un `except TimeoutError` no casa con un grupo:
        #
        #     ExceptionGroup: 'unhandled errors in a TaskGroup'
        #       ExceptionGroup: 'unhandled errors in a TaskGroup'
        #         TimeoutError          <- lo que de verdad pasó
        #
        # Ese envoltorio no se puede desactivar: es la semántica de los task
        # groups, donde pueden fallar VARIAS tareas a la vez y no existe «la»
        # excepción que devolver.
        #
        # `except*` (Python 3.11+) desmonta el grupo y compara por tipo a
        # CUALQUIER profundidad, así que cubre también el caso sin envolver y no
        # depende de cuántas capas ponga la librería el día de mañana.
        #
        # Diferencia con un `except` normal, comprobada: `except*` puede entrar
        # en VARIAS ramas, porque un grupo admite fallos de tipos distintos. Si
        # llegara un timeout JUNTO A otro fallo, saldría un grupo con el
        # `ToolTimeout` dentro y quien llame vería un fallo genérico en lugar de
        # un timeout. Se asume: un timeout más un fallo independiente no es
        # realmente «no respondió a tiempo».
        except* TimeoutError:
            log.warning("tool.execute.timeout", tool=name, url=url)
            raise ToolTimeout(name) from None

        if intento is None:
            continue  # esta herramienta no está en este servidor

        problemas, resultado, servidor = intento
        if problemas:
            raise InvalidArguments(problemas)
        if resultado is None:
            # `_intentar` devuelve resultado siempre que no haya problemas, pero
            # eso es un acuerdo entre las dos funciones que la tupla no expresa.
            # Si alguien rompe el acuerdo, mejor aquí que tres marcos más abajo.
            raise RuntimeError(f"«{name}» no devolvió resultado ni problemas.")

        return _leer(resultado, name, servidor)

    raise ToolNotFound(name)


async def discover_all(
    servers: Sequence[str], timeout: float
) -> list[ServerCatalog | BaseException]:
    """Consulta todos los servidores a la vez; un fallo no tumba a los demás.

    Devuelve una lista **del mismo largo y en el mismo orden** que ``servers``:
    cada posición trae su catálogo o la excepción que impidió obtenerlo. Quien
    llame decide qué hacer con el fallo — la API lo publica como servidor
    inalcanzable, y el agente probablemente lo ignore y siga con el resto.

    La degradación vive aquí y no en la fachada porque es política del
    mecanismo, no del transporte: un catálogo parcial es útil, y el segundo
    consumidor querrá lo mismo sin volver a escribirlo.
    """
    return await asyncio.gather(
        *(_consultar(url, timeout) for url in servers),
        return_exceptions=True,
    )


async def _consultar(url: str, timeout: float) -> ServerCatalog:
    """Abre una sesión MCP, se presenta y pide el catálogo de ese servidor.

    El ``asyncio.timeout`` es el que hace verdad el corte: que un servidor lento
    salga como fallo en vez de dejar la consulta colgada. El ``timeout`` de
    httpx no basta —mide inactividad entre bytes, no duración— y sin esto un
    servidor que acepta la conexión y tarda en responder cuelga la petición para
    siempre.

    Lo que sí cubría httpx, y sigue cubriendo, es el servidor **caído**: ahí la
    conexión se rechaza y falla rápido.
    """
    async with (
        asyncio.timeout(timeout),
        open_session(url, timeout) as (session, inicializacion),
    ):
        listado = await session.list_tools()

    return ServerCatalog(
        url=url,
        server=inicializacion.serverInfo.name,
        tools=list(listado.tools),
    )


async def _intentar(
    url: str, name: str, arguments: dict, timeout: float
) -> tuple[str | None, CallToolResult | None, str] | None:
    """Busca la herramienta en un servidor y, si está, la valida y la invoca.

    Devuelve ``None`` si no la tiene. Si la tiene, ``(problemas, resultado,
    servidor)``: con ``problemas`` los argumentos no pasaron la validación y no
    se llegó a invocar nada.

    El ``asyncio.timeout`` acota **la operación entera** —handshake, catálogo y
    llamada— y no sólo ``call_tool``, para que un servidor lento en presentarse
    tampoco deje la petición sin techo.

    Es el que de verdad corta. El ``timeout`` de httpx que se le pasa a
    ``open_session`` mide **inactividad entre bytes**, no duración: con una tool
    que tarda más de la cuenta no salta, y la petición se queda colgada para
    siempre en vez de fallar (#113, reproducido — 25 s de espera con un corte
    pedido de 2). Se conserva igualmente porque sí cubre lo suyo: un servidor que
    acepta la conexión y deja de enviar.
    """
    async with (
        asyncio.timeout(timeout),
        open_session(url, timeout) as (session, inicializacion),
    ):
        tools = {t.name: t for t in (await session.list_tools()).tools}
        if name not in tools:
            return None

        servidor = inicializacion.serverInfo.name
        problemas = _problemas(arguments, tools[name])
        if problemas:
            return problemas, None, servidor

        return None, await session.call_tool(name, arguments), servidor


def _problemas(arguments: dict, tool: Tool) -> str | None:
    """Valida los argumentos contra el ``inputSchema``; None si están bien.

    **Se valida antes de invocar** (R4.5), contra el esquema que el propio
    servidor publica. Se podría dejar que validara MCP, pero entonces un
    argumento mal escrito llegaría como fallo de ejecución y sería
    indistinguible de un análisis que salió mal.

    Se acumulan **todos** los problemas en vez de parar en el primero: quien
    rellena un formulario prefiere corregirlo de una vez a descubrirlos de uno
    en uno.
    """
    errores = sorted(
        Draft7Validator(tool.inputSchema).iter_errors(arguments),
        key=lambda e: list(e.path),
    )
    if not errores:
        return None

    return "; ".join(
        f"{'.'.join(str(p) for p in e.path) or '(raíz)'}: {e.message}" for e in errores
    )


def _leer(resultado: CallToolResult, name: str, servidor: str) -> Invocation:
    """Traduce la respuesta del protocolo al resultado neutro.

    ``isError`` es fiable desde que las herramientas **lanzan** en vez de
    devolver el mensaje de error: antes un fallo llegaba por el mismo canal que
    un resultado válido y aquí no habría forma de distinguirlos.
    """
    if resultado.isError:
        # El contenido de MCP es una unión —texto, imagen, audio, recurso— y
        # sólo el de texto tiene `.text`. Leerlo a ciegas funcionaba porque
        # nuestras tools sólo devuelven texto, pero un servidor ajeno que
        # respondiera con otra cosa habría reventado aquí en vez de informar.
        primero = resultado.content[0] if resultado.content else None
        motivo = (
            primero.text if isinstance(primero, TextContent) else "Error desconocido"
        )
        log.warning("tool.execute.failed", tool=name, motivo=motivo)
        return Invocation(server=servidor, result=ToolResult.fail(motivo))

    return Invocation(
        server=servidor, result=ToolResult.ok(resultado.structuredContent)
    )
