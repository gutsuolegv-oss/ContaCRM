"""Configurația aplicației. Toate valorile vin din variabile de mediu (.env)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
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

    # Doar pentru dezvoltare prin HTTP simplu pe rețeaua locală (ex. http://192.168.x.x:5173):
    # false = cookie-ul de sesiune fără atributul Secure. Interzis în producție.
    session_cookie_secure: bool | None = None

    @model_validator(mode="after")
    def _no_insecure_cookie_in_prod(self) -> Self:
        if self.environment == "prod" and self.session_cookie_secure is False:
            raise ValueError("SESSION_COOKIE_SECURE=false nu e permis în producție")
        return self

    @property
    def cookie_secure(self) -> bool:
        """Cookie-ul de sesiune doar pe HTTPS. Excepții: testele (clientul HTTP de test nu
        folosește HTTPS) și SESSION_COOKIE_SECURE=false în dezvoltare. Prin http://localhost
        (tunel SSH) merge și cu Secure: browserele tratează localhost ca sigur."""
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.environment != "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # câmpurile obligatorii vin din mediu
