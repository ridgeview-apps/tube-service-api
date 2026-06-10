from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["system"])


class HealthRead(BaseModel):
    status: str


@router.get("/health", response_model=HealthRead)
async def health() -> HealthRead:
    return HealthRead(status="ok")
