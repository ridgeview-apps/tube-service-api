from fastapi import FastAPI

from app.api.router import router

app = FastAPI(
    title="Tube Service API",
    version="0.1.0",
)
app.include_router(router)
