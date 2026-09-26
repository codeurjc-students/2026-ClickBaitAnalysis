"""El agente conversacional: el bucle de *tool calling* sobre el descubrimiento
MCP (#188, R13).

Recibe una consulta y el texto de los turnos anteriores, descubre las
herramientas por MCP, deja que el modelo pida las que necesite, las ejecuta y le
devuelve los resultados, hasta que responde o se agotan las vueltas. El
esqueleto es el del spike (`spikes/tool_calling_fase3.py`); el plano, §12 de
`docs/arquitectura.md`.

Lo que no se deduce leyendo el bucle:

- **El veredicto no pasa por aquí** (R13.4). El modelo narra; las tarjetas
  salen del resultado de cada herramienta, que va ENTERO a la traza. Lo que lee
  el modelo se puede recortar (`max_result_chars`); la traza, nunca.
- **No lee `settings`**: recibe backend, servidores, prompt y cortes en
  `Configuracion` (regla de #119), y `tests/test_arquitectura.py` lo vigila. Lo
  monta la API (#189).
- **Avisa de cada paso según ocurre**, con `al_paso`, y no sabe quién escucha:
  la API lo usará para que la traza crezca mientras la interfaz sondea.
- **Un error de una herramienta vuelve al modelo como resultado**, para que
  pueda corregir los argumentos o contarlo, y va a la traza como mensaje
  público. Lo imprevisto se registra entero ANTES de publicar la frase (#89).
- **Cada herramienta se ejecuta en el servidor que la publicó**, no buscándola
  en todos: `execute_tool` recorre los servidores en orden, y uno caído lo haría
  fallar antes de llegar al bueno. Por eso el catálogo se descubre una vez por
  consulta y guarda de dónde vino cada herramienta.
- **Como mucho seis vueltas**, como en el spike. Agotadas, termina con la traza
  entera y sin narración, y las tarjetas salen igual (R6.13).
- **El modelo razona antes de contestar (`think=True`), y es explícito.**
  Medido en la A40 el 2026-09-26 (`spikes/agente_a40.py`): sin razonar, el 27B
  eligió bien 13 de 26 consultas y en los fallos **se inventó el resultado de
  las herramientas sin llamarlas**, con posiciones y probabilidades falsas.
  Razonando, 25/26. Sin mandar el campo, como el spike, también 25/26 y con
  una salida parecida: todo indica que Ollama razona por defecto con este
  modelo, y que el spike se midió así sin saberlo. Se escribe igualmente, como
  `num_ctx`, para no depender del defecto.
- **Las descripciones se envían sin la sangría del docstring**, que FastMCP
  manda tal cual: son espacios que el modelo paga en cada petición y no dicen
  nada. Lo que enseña la pantalla de Sistema no cambia.
"""

import inspect
import json
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import structlog

from backend.agent.traza import (
    EstadoFinal,
    Paso,
    PasoHerramienta,
    Resultado,
    Turno,
)
from backend.core.errores import describir_error, mensaje_publico
from backend.core.mcp import tools
from backend.integrations.llm.base import (
    Herramienta,
    LlamadaHerramienta,
    LLMBackend,
    Mensaje,
    Respuesta,
)

log = structlog.get_logger()

# El cortafuegos del spike: un agente que no converge no debe girar sin fin. En
# el spike, los bucles completos no pasaron de 2–3 vueltas.
MAX_VUELTAS = 6

SIN_HERRAMIENTAS = (
    "No se pudo consultar ninguna herramienta, así que el asistente no tiene con "
    "qué analizar."
)


@dataclass(frozen=True)
class Configuracion:
    """Todo lo que el agente necesita, dado por quien lo monta.

    Dos cortes y no uno, como en la API: descubrir tarda milésimas, y ejecutar
    puede tener que cargar un modelo la primera vez (`mcp_execute_timeout`).

    `max_result_chars` acota lo que el MODELO lee de cada resultado, y va
    `None`, entero, por lo medido en la A40: el bucle más largo (una noticia y
    su análisis completo) llegó a 5.842 de 8.192 tokens; y recortando a 1.500
    caracteres, como el spike, el corte cayó en mitad de un valor —el modelo
    leyó `"incoherent": fa`— y dejó fuera el umbral y el veredicto global, y
    el modelo llamó «incoherente» a una similitud de 0,311 con umbral 0,3. Se
    conserva para poder reproducir esa medida.
    """

    backend: LLMBackend
    servers: Sequence[str]
    prompt: str
    discovery_timeout: float
    execute_timeout: float
    max_rounds: int = MAX_VUELTAS
    think: bool = True
    max_result_chars: int | None = None


# Cada herramienta del catálogo, con la URL del servidor que la publicó.
Catalogo = dict[str, tuple[Herramienta, str]]


async def responder(
    consulta: str,
    historial: Sequence[Turno],
    config: Configuracion,
    al_paso: Callable[[Paso], None] | None = None,
) -> Resultado:
    """Contesta una consulta usando las herramientas que el modelo pida."""
    inicio = time.perf_counter()
    pasos: list[Paso] = []

    def anotar(paso: Paso) -> None:
        pasos.append(paso)
        if al_paso is not None:
            al_paso(paso)

    def terminar(
        status: EstadoFinal, rounds: int, answer: str = "", detail: str | None = None
    ) -> Resultado:
        total = time.perf_counter() - inicio
        log.info(
            "agent.fin",
            estado=status,
            vueltas=rounds,
            herramientas=sum(paso["kind"] == "tool" for paso in pasos),
            total_s=round(total, 2),
        )
        return {
            "status": status,
            "answer": answer,
            "detail": detail,
            "steps": pasos,
            "rounds": rounds,
            "total_s": total,
        }

    catalogo = await _descubrir(config)
    if not catalogo:
        return terminar("failed", rounds=0, detail=SIN_HERRAMIENTAS)
    herramientas = [herramienta for herramienta, _ in catalogo.values()]

    mensajes: list[Mensaje] = [
        {"role": "system", "content": config.prompt},
        *({"role": turno["role"], "content": turno["content"]} for turno in historial),
        {"role": "user", "content": consulta},
    ]

    for vuelta in range(1, config.max_rounds + 1):
        resultado = await config.backend.chat(
            mensajes, herramientas, think=config.think
        )
        if not resultado.success:
            # El cliente ya lo redactó para publicarse (#185).
            return terminar("failed", rounds=vuelta, detail=resultado.error)

        respuesta: Respuesta = resultado.unwrap()
        pedidas = [llamada["name"] for llamada in respuesta["tool_calls"]]
        anotar(
            {
                "kind": "model",
                "round": vuelta,
                "content": respuesta["content"],
                "tool_calls": pedidas,
                "metrics": respuesta["metrics"],
            }
        )
        log.info(
            "agent.vuelta",
            vuelta=vuelta,
            pide=pedidas,
            prompt_tokens=respuesta["metrics"]["prompt_tokens"],
            total_s=round(respuesta["metrics"]["total_s"], 2),
        )

        if not respuesta["tool_calls"]:
            if respuesta["content"].strip():
                return terminar("answered", rounds=vuelta, answer=respuesta["content"])
            return terminar("empty_answer", rounds=vuelta)

        mensajes.append(
            {
                "role": "assistant",
                "content": respuesta["content"],
                "tool_calls": respuesta["tool_calls"],
            }
        )
        for llamada in respuesta["tool_calls"]:
            paso = await _ejecutar(llamada, vuelta, catalogo, config.execute_timeout)
            anotar(paso)
            mensajes.append(
                {
                    "role": "tool",
                    "tool_name": llamada["name"],
                    "content": _para_el_modelo(paso, config.max_result_chars),
                }
            )

    return terminar("max_rounds", rounds=config.max_rounds)


async def _descubrir(config: Configuracion) -> Catalogo:
    """El catálogo de todos los servidores que respondan; los caídos se saltan.

    Si dos servidores publican el mismo nombre, gana el primero de la lista: es
    el mismo orden en que los recorre `execute_tool`.
    """
    catalogos = await tools.discover_all(config.servers, config.discovery_timeout)
    encontradas: Catalogo = {}
    for url, catalogo in zip(config.servers, catalogos, strict=True):
        if isinstance(catalogo, BaseException):
            log.warning(
                "agent.servidor_inalcanzable",
                url=url,
                motivo=describir_error(catalogo),
            )
            continue
        for tool in catalogo.tools:
            herramienta: Herramienta = {
                "name": tool.name,
                "description": inspect.cleandoc(tool.description or ""),
                "parameters": tool.inputSchema,
            }
            encontradas.setdefault(tool.name, (herramienta, url))
    return encontradas


async def _ejecutar(
    llamada: LlamadaHerramienta, vuelta: int, catalogo: Catalogo, corte: float
) -> PasoHerramienta:
    """Ejecuta una herramienta y cuenta cómo fue, sin lanzar nunca.

    Cada final posible acaba en un paso: el modelo necesita saber qué pasó para
    corregirse, y la interfaz, para enseñarlo. Los mensajes de error son
    públicos, así que nunca llevan el texto de una excepción de librería (#163).
    """
    nombre, argumentos = llamada["name"], llamada["arguments"]
    inicio = time.perf_counter()
    servidor: str | None = None
    datos = None
    error: str | None = None

    if nombre not in catalogo:
        error = f"No hay ninguna herramienta llamada «{nombre}» en el catálogo."
    else:
        _, url = catalogo[nombre]
        try:
            invocacion = await tools.execute_tool(
                nombre, argumentos, servers=[url], timeout=corte
            )
        except tools.InvalidArguments as problemas:
            # El mismo texto que publica el 422 de `/tools/{name}/execute`: son
            # los mensajes del validador sobre los argumentos del propio modelo.
            error = (
                f"Los argumentos no encajan en el esquema de «{nombre}»: {problemas}"
            )
        except tools.ToolTimeout:
            error = f"«{nombre}» tardó demasiado en responder."
        except tools.ToolNotFound:
            error = f"«{nombre}» ya no está en el servidor que la publicó."
        except Exception as excepcion:
            log.error(
                "agent.herramienta.imprevisto",
                herramienta=nombre,
                tipo=type(excepcion).__name__,
                detalle=str(excepcion),
                traza="".join(traceback.format_exception(excepcion)),
            )
            error = f"«{nombre}» {mensaje_publico(excepcion)}."
        else:
            servidor = invocacion.server
            if invocacion.result.success:
                datos = invocacion.result.data
            else:
                # Las herramientas lanzan mensajes ya redactados para publicarse
                # (#89, #185); `_leer` los trae tal cual.
                error = (
                    invocacion.result.error or f"«{nombre}» falló sin decir por qué."
                )

    duracion = time.perf_counter() - inicio
    log.info(
        "agent.herramienta",
        herramienta=nombre,
        estado="error" if error else "ok",
        duracion_s=round(duracion, 2),
    )
    return {
        "kind": "tool",
        "round": vuelta,
        "name": nombre,
        "arguments": argumentos,
        "status": "error" if error else "ok",
        "data": datos,
        "error": error,
        "server": servidor,
        "duration_s": duracion,
    }


def _para_el_modelo(paso: PasoHerramienta, max_chars: int | None) -> str:
    """Lo que el modelo lee de un resultado: el JSON, entero o recortado.

    Un recorte lo DICE, con el tamaño total: un JSON cortado sin aviso invita a
    completar de memoria lo que falta, que es justo lo que no puede hacer (R13.4).
    """
    if paso["status"] == "error":
        return json.dumps({"error": paso["error"]}, ensure_ascii=False)

    texto = json.dumps(paso["data"], ensure_ascii=False, default=str)
    if max_chars is None or len(texto) <= max_chars:
        return texto
    return (
        f"{texto[:max_chars]}… [recortado: el resultado tiene {len(texto)} caracteres]"
    )
