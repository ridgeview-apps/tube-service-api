from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./tube_service.db"
    tfl_api_key: str | None = None
    poll_interval_seconds: int = Field(default=600, ge=30)


@lru_cache
def get_settings() -> Settings:
    return Settings()
