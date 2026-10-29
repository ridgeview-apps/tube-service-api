import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine

router = APIRouter(tags=["system"])


class HealthRead(BaseModel):
    status: str


class ReadinessRead(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthRead)
async def health() -> HealthRead:
    return HealthRead(status="ok")


@router.get("/ready", response_model=ReadinessRead)
async def readiness() -> ReadinessRead | JSONResponse:
    try:
        async with asyncio.timeout(2):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError, TimeoutError):
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": {"database": "unavailable"}},
        )

    return ReadinessRead(status="ready", checks={"database": "ok"})
