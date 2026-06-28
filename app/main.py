from fastapi import FastAPI

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
