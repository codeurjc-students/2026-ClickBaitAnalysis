"""Las conversaciones con el asistente, como trabajos en memoria (#189).

`POST /chat` crea un trabajo y devuelve su id al instante; el agente trabaja en
segundo plano y la traza crece paso a paso; `GET /chat/{id}` la lee. Es de
`api/` y no de `agent/` porque sin HTTP no existiría: el agente sólo AVISA de
cada paso (`al_paso`) y no sabe quién escucha (decidido al definir H5).

Lo que no se deduce leyéndolo:

- **Una conversación en ejecución; las demás, en una cola visible.** La GPU es
  una. Si la cola la hiciera Ollama, la espera sería invisible para quien
  sondea y se comería el `llm_timeout` de cada llamada, que cuenta desde que se
  envía: una conversación detrás de otra podría caducar sin haber empezado. Con
  la cola llena se rechaza en vez de aceptar sin límite.
- **En memoria, porque el backend va con un solo worker** desde #125. Con dos,
  el sondeo caería a veces en el proceso que no tiene el trabajo.
- **Se guarda la referencia a cada tarea**: el bucle de eventos sólo guarda una
  débil, y una tarea sin referencias puede desaparecer a mitad.
- **Sólo caducan y se descartan los terminados.** Olvidar uno en marcha dejaría
  a quien sondea con un 404 de algo que sigue ocupando la GPU.
- **El id no se puede adivinar**: la aplicación no tiene autenticación, y quien
  tiene el id lee la conversación. Uno secuencial dejaría leer las de otros.
- **Un fallo imprevisto se registra entero ANTES de publicar la frase** (#89).
"""

import asyncio
import secrets
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from backend.agent import prompts
from backend.agent.agente import Configuracion, responder
from backend.agent.traza import Paso, Resultado, Turno
from backend.api.schemas import ChatJob, ChatOutcome, ChatStatus
from backend.config.settings import settings
from backend.core.errores import mensaje_publico
from backend.integrations.llm.factory import get_llm_backend

log = structlog.get_logger()


class ColaLlena(Exception):
    """No cabe otra conversación: una en marcha y la cola llena."""


@dataclass
class Trabajo:
    """Una conversación en curso o terminada. La consulta no se publica."""

    id: str
    consulta: str
    creado: datetime
    status: ChatStatus = ChatStatus.QUEUED
    pasos: list[Paso] = field(default_factory=list)
    resultado: Resultado | None = None
    terminado_en: float | None = None  # del reloj del almacén, para caducar


class Trabajos:
    """Las conversaciones del proceso, con su cola, su caducidad y su tope.

    El reloj se INYECTA, como en el limitador de #169, para que las pruebas
    adelanten el tiempo en vez de dormir quince minutos.
    """

    def __init__(
        self,
        *,
        en_cola: int,
        caducidad_s: float,
        maximo: int,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._en_cola = en_cola
        self._caducidad_s = caducidad_s
        self._maximo = maximo
        self._reloj = reloj
        self._trabajos: dict[str, Trabajo] = {}
        self._tareas: set[asyncio.Task[None]] = set()
        self._turno = asyncio.Semaphore(1)

    def lanzar(
        self, consulta: str, historial: Sequence[Turno], config: Configuracion
    ) -> Trabajo:
        """Crea el trabajo y lo pone en marcha, o en cola. Lanza `ColaLlena`."""
        self._olvidar_caducados()
        pendientes = sum(
            trabajo.status != ChatStatus.DONE for trabajo in self._trabajos.values()
        )
        if pendientes >= 1 + self._en_cola:
            raise ColaLlena

        trabajo = Trabajo(
            id=secrets.token_urlsafe(16), consulta=consulta, creado=datetime.now(UTC)
        )
        self._trabajos[trabajo.id] = trabajo
        self._recortar()

        tarea = asyncio.create_task(self._ejecutar(trabajo, historial, config))
        self._tareas.add(tarea)
        tarea.add_done_callback(self._tareas.discard)
        log.info("chat.aceptada", trabajo=trabajo.id, en_espera=pendientes)
        return trabajo

    def leer(self, trabajo_id: str) -> Trabajo | None:
        """El trabajo con ese id, o `None` si no existe o ya caducó."""
        self._olvidar_caducados()
        return self._trabajos.get(trabajo_id)

    async def _ejecutar(
        self, trabajo: Trabajo, historial: Sequence[Turno], config: Configuracion
    ) -> None:
        async with self._turno:
            trabajo.status = ChatStatus.RUNNING
            inicio = time.perf_counter()
            resultado: Resultado
            try:
                resultado = await responder(
                    trabajo.consulta, historial, config, al_paso=trabajo.pasos.append
                )
            except Exception as excepcion:
                log.error(
                    "chat.imprevisto",
                    trabajo=trabajo.id,
                    tipo=type(excepcion).__name__,
                    detalle=str(excepcion),
                    traza="".join(traceback.format_exception(excepcion)),
                )
                resultado = {
                    "status": "failed",
                    "answer": "",
                    "detail": f"El asistente {mensaje_publico(excepcion)}.",
                    "steps": trabajo.pasos,
                    "rounds": sum(paso["kind"] == "model" for paso in trabajo.pasos),
                    "total_s": time.perf_counter() - inicio,
                }
            trabajo.resultado = resultado
            trabajo.status = ChatStatus.DONE
            trabajo.terminado_en = self._reloj()

    def _olvidar_caducados(self) -> None:
        ahora = self._reloj()
        caducados = [
            trabajo_id
            for trabajo_id, trabajo in self._trabajos.items()
            if trabajo.terminado_en is not None
            and ahora - trabajo.terminado_en >= self._caducidad_s
        ]
        for trabajo_id in caducados:
            del self._trabajos[trabajo_id]

    def _recortar(self) -> None:
        """Por encima del tope, olvida los terminados más antiguos."""
        terminados = [
            trabajo_id
            for trabajo_id, trabajo in self._trabajos.items()
            if trabajo.status == ChatStatus.DONE
        ]
        sobran = len(self._trabajos) - self._maximo
        for trabajo_id in terminados[: max(0, sobran)]:
            del self._trabajos[trabajo_id]


def configuracion() -> Configuracion | None:
    """La configuración del agente que dicen los ajustes AHORA, o `None` si no
    hay agente. La monta la API: el agente no lee `settings` (#119)."""
    backend = get_llm_backend()
    if backend is None:
        return None
    return Configuracion(
        backend=backend,
        servers=settings.mcp_servers,
        prompt=prompts.cargar(settings.llm_prompt),
        discovery_timeout=settings.mcp_timeout,
        execute_timeout=settings.mcp_execute_timeout,
    )


def como_respuesta(trabajo: Trabajo) -> ChatJob:
    """Traduce un trabajo al contrato de `GET /chat/{id}`."""
    resultado = trabajo.resultado
    return ChatJob(
        id=trabajo.id,
        status=trabajo.status,
        created_at=trabajo.creado,
        steps=list(trabajo.pasos),
        result=None
        if resultado is None
        else ChatOutcome(
            status=resultado["status"],
            answer=resultado["answer"],
            detail=resultado["detail"],
            rounds=resultado["rounds"],
            total_s=resultado["total_s"],
        ),
    )


_trabajos: Trabajos | None = None


def obtener_trabajos() -> Trabajos:
    """El almacén del proceso, construido en el primer uso con los ajustes de
    entonces, por lo mismo que el limitador: al importar sería una constante."""
    global _trabajos
    if _trabajos is None:
        _trabajos = Trabajos(
            en_cola=settings.chat_queue_size,
            caducidad_s=settings.chat_job_ttl_s,
            maximo=settings.chat_max_jobs,
        )
    return _trabajos


def reiniciar_trabajos() -> None:
    """Olvida todas las conversaciones. La usan las pruebas: es estado de módulo."""
    global _trabajos
    _trabajos = None
