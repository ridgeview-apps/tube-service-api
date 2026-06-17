from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_api_key
from app.database import get_session
from app.operations.repository import get_latest_worker_runs
from app.operations.schemas import WorkerRunsRead

router = APIRouter(
    prefix="/v1/operations",
    tags=["operations"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/workers", response_model=WorkerRunsRead)
async def worker_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkerRunsRead:
    return WorkerRunsRead(workers=await get_latest_worker_runs(session))
