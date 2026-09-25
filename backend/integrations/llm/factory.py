"""Qué modelo de lenguaje hay configurado de verdad: el backend, si está
disponible y qué ficha se publica.

Como `nlp/factory.py`, es el ÚNICO módulo de este paquete que lee `settings`, y
`tests/test_arquitectura.py` lo vigila: el cliente recibe su configuración, así
que se prueba sin montar un entorno.

`llm_backend` vale `None` por defecto, y entonces no hay agente: es el estado
«sin configurar» de R6.10 y R6.14, distinto de «configurado pero apagado», que
es lo normal cuando nadie tiene abierta una sesión en la máquina de la GPU.
"""

from functools import lru_cache

from backend.config.settings import settings
from backend.integrations.llm.base import Disponibilidad, LLMBackend
from backend.integrations.llm.model_card import FICHA, FichaLLM
from backend.integrations.llm.ollama import OllamaClient


@lru_cache(maxsize=4)
def _backend_para(
    backend: str,
    url: str,
    model: str,
    num_ctx: int,
    keep_alive: str,
    timeout: float,
) -> LLMBackend:
    """Un cliente por configuración, construido la primera vez que hace falta.

    **La clave de caché es la configuración entera** (#119): cambiar un ajuste
    produce otro cliente, y nadie queda atado a lo que hubiera al importar.
    """
    match backend:
        case "ollama":
            return OllamaClient(
                url, model, num_ctx=num_ctx, keep_alive=keep_alive, timeout=timeout
            )
        case _:
            raise ValueError(f"Backend de modelo de lenguaje desconocido: {backend}")


def get_llm_backend() -> LLMBackend | None:
    """El backend que dice la configuración AHORA, o `None` si no hay agente."""
    if settings.llm_backend is None:
        return None
    return _backend_para(
        settings.llm_backend,
        settings.llm_url,
        settings.llm_model,
        settings.llm_num_ctx,
        settings.llm_keep_alive,
        settings.llm_timeout,
    )


async def disponibilidad() -> Disponibilidad:
    """Si el asistente se puede usar ahora, con los cuatro estados de R6.14."""
    backend = get_llm_backend()
    if backend is None:
        return Disponibilidad(
            "not_configured",
            "El asistente no está configurado en este despliegue.",
        )
    return await backend.disponibilidad()


def ficha_efectiva() -> FichaLLM:
    """La ficha que se publica, con el modelo que se usa de verdad.

    Si el modelo configurado no es el de la ficha, se publica el configurado y
    las limitaciones medidas NO: eran de otro modelo (#119). Sobrevive lo que
    describe el hueco —la tarea y el tipo—, no a su ocupante.
    """
    configurado = settings.llm_model
    if configurado == FICHA["model_id"]:
        return FICHA

    return {
        **FICHA,
        "model_id": configurado,
        "name": f"{configurado} (puesto por configuración)",
        "limitations": [
            f"SIN EVALUAR EN ESTE PROYECTO. Este modelo se ha puesto por configuración en lugar de `{FICHA['model_id']}`, así que las limitaciones medidas de aquél no se publican aquí: eran suyas. Lo que sigue siendo cierto es lo que describe el hueco y no al modelo: es de tipo `{FICHA['type']}`, y el veredicto no es suyo.",
        ],
    }
