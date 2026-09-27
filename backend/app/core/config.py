"""Configurația aplicației. Toate valorile vin din variabile de mediu (.env)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "prod"

    database_url: str
    redis_url: str = "redis://redis:6379/0"

    app_secret_key: SecretStr = Field(min_length=32)

    # Fusul orar al biroului: „azi” pentru termene, valid_from implicit etc.
    timezone: str = "Europe/Chisinau"

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    @property
    def cookie_secure(self) -> bool:
        """Cookie-ul de sesiune doar pe HTTPS. Excepție: testele (clientul HTTP de test nu
        folosește HTTPS). În dezvoltare merge prin http://localhost (tunel SSH), pe care
        browserele îl tratează ca sigur."""
        return self.environment != "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # câmpurile obligatorii vin din mediu
