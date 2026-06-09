from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.database import create_tables


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await create_tables()
    yield


app = FastAPI(
    title="Tube Service History API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
