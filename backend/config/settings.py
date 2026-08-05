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


settings = Settings()  # type: ignore #Activa la validación al importar
