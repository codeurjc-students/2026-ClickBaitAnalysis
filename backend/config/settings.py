#Base Settings: Base class for settings, allowing values to be overridden by environment variables.

# This is useful in production for secrets you do not wish to save in code, it plays nicely with docker(-compose),
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore") #Ignora valores extra añadidos, solo valida lo declarado. Util si se añaden más API-KEYS
    guardian_api_key: str # PS mapea automáticamente
    
    
settings = Settings() # type: ignore #Activa la validación al importar
    
