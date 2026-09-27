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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # câmpurile obligatorii vin din mediu
