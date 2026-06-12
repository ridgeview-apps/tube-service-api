from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    provided_api_key: Annotated[str | None, Depends(api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    configured_api_keys = settings.client_api_keys
    if not configured_api_keys:
        if settings.app_env == "development":
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured",
        )

    if provided_api_key is None or "." not in provided_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    client_id, provided_secret = provided_api_key.split(".", maxsplit=1)
    configured_secrets = configured_api_keys.get(client_id, [])
    if not any(
        compare_digest(
            provided_secret.encode(),
            configured_secret.get_secret_value().encode(),
        )
        for configured_secret in configured_secrets
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
