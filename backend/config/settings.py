# Base Settings: Base class for settings, allowing values to be overridden by environment variables.

# This is useful in production for secrets you do not wish to save in code, it plays nicely with docker(-compose),
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )  # Ignora valores extra añadidos, solo valida lo declarado. Util si se añaden más API-KEYS

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"
    guardian_api_key: str  # PS mapea automáticamente
    nyt_api_key: str
    hf_token: str
    nlp_backend: Literal["remote", "local"] = (
        "remote"  # Añadimos dos opciones de backend NLP, así mantenemos remoto sin cambiar mucho.
    )

    # Orígenes permitidos por CORS. Configurable porque el frontend vive
    # en localhost:4200 en desarrollo pero no en despliegue. Desde el
    # entorno se pasa como JSON: CORS_ORIGINS='["https://ejemplo.org"]'
    cors_origins: list[str] = ["http://localhost:4200"]

    # Transporte del servidor MCP.
    #
    # `stdio` es el valor por defecto porque es lo que espera un cliente que
    # lanza el servidor como SUBPROCESO y habla con él por tuberías — así está
    # conectado hoy en local. Cambiar el defecto rompería esa conexión.
    #
    # `streamable-http` lo expone por red, que es la precondición para
    # desplegarlo como contenedor independiente: stdio no cruza contenedores,
    # porque exige que el cliente sea quien arranca el proceso.
    #
    # host/port sólo los usa el transporte HTTP; con stdio son inertes.
    mcp_transport: Literal["stdio", "streamable-http"] = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    # Servidores MCP que consulta la API para construir el catálogo.
    #
    # Es una LISTA aunque hoy tenga un elemento:sirve para agregar los
    # catálogos de todos los servidores conectados indicando el origen de cada
    # herramienta, y pasar de `str` a `list[str]` más tarde tocaría a la vez la
    # configuración, el catálogo y su contrato. Cuesta lo mismo ahora.
    #
    # Desde el entorno se pasa como JSON:
    #   MCP_SERVERS='["http://mcp:8765/mcp","http://otro:8765/mcp"]'
    mcp_servers: list[str] = ["http://127.0.0.1:8765/mcp"]

    # Corte para dar un servidor por inalcanzable. Sin él, un servidor que acepta
    # la conexión y no responde dejaría /tools colgado en vez de degradado.
    mcp_timeout: float = 5.0

    # Ejecutar una herramienta necesita mucho más margen que descubrirla: un
    # `list_tools` tarda milésimas, pero `detect_clickbait_incoherence` puede
    # tardar ~20 s la primera vez porque carga el modelo de embeddings. Con el
    # timeout de descubrimiento, esa llamada moriría siempre en frío.
    mcp_execute_timeout: float = 60.0

    # Fichero SQLite del historial.
    #
    # Va en `var/` y no en `data/` a propósito: `data/` está versionado —guarda
    # los datasets y los splits congelados, que no deben cambiar nunca— y esto
    # es estado mutable que cambia en cada petición. Juntarlos acabaría en un
    # `git add data/` que commitea la base de datos.
    #
    # Este directorio es el que se monta como volumen luego para que el
    # historial sobreviva al contenedor.
    history_db: str = "var/history.db"

    # Retención del historial. `0` desactiva cada límite por separado.
    #
    # Son configuración y no constantes porque el criterio propone «las últimas
    # 1000 ejecuciones o 30 días» COMO EJEMPLO, no como norma. Y porque en
    # desarrollo interesa desactivarlos (`HISTORY_MAX_ENTRIES=0`) para no perder
    # las pruebas propias entre sesiones.
    #
    # Se aplican los dos: manda el más estricto. Uno acota el TAMAÑO pero no el
    # horizonte temporal —mil análisis de golpe borran los de ayer— y el otro
    # acota el horizonte pero no el tamaño —una ráfaga de 50 000 cabe entera en
    # 30 días—. Cada uno tapa el punto ciego del otro.
    #
    # No es sólo higiene de disco: `GET /history` cuenta las filas en cada
    # lectura y ese conteo es LINEAL (~1 µs por fila, medido). Sin techo, a
    # 50 000 entradas cada petición gasta 50 ms sólo en contar.
    history_max_entries: int = 1000
    history_max_days: int = 30


settings = Settings()  # type: ignore #Activa la validación al importar
