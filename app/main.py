from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api.router import router
from app.config import get_settings
from app.http_debug import HttpDebugMiddleware

settings = get_settings()

app = FastAPI(
    title="Tube Service API",
    version="0.1.0",
)
if settings.http_debug_logging:
    app.add_middleware(
        HttpDebugMiddleware,
        body_limit=settings.http_debug_body_limit,
    )
app.include_router(router)


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    # FastAPI's OpenAPI serialization excludes None values globally, including in
    # examples. JSON Merge Patch needs a literal null to demonstrate deletion.
    schema["paths"]["/v1/notification-devices/{device_id}/preferences"]["patch"]["requestBody"][
        "content"
    ]["application/merge-patch+json"]["examples"]["update-and-remove"]["value"]["lines"][
        "central"
    ] = None
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
