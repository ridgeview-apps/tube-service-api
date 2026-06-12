from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
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
    client_api_keys: dict[str, list[SecretStr]] = Field(default_factory=dict)
    poll_interval_seconds: int = Field(default=600, ge=30)
    history_cache_today_ttl_seconds: int = Field(default=120, ge=0)
    history_cache_past_ttl_seconds: int = Field(default=3600, ge=0)

    @field_validator("client_api_keys")
    @classmethod
    def validate_client_api_keys(
        cls,
        value: dict[str, list[SecretStr]],
    ) -> dict[str, list[SecretStr]]:
        for client_id, secrets in value.items():
            if not client_id or "." in client_id:
                raise ValueError("Client IDs must be non-empty and cannot contain '.'")
            if not secrets:
                raise ValueError(f"Client '{client_id}' must have at least one API key")
            if any(len(secret.get_secret_value()) < 32 for secret in secrets):
                raise ValueError("Client API keys must be at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
