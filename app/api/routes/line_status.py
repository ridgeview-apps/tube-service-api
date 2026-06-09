from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.line_status.schemas import DailyHistoryResponse
from app.line_status.service import get_daily_history

router = APIRouter(prefix="/v1/line-status", tags=["line status"])


@router.get("/history", response_model=DailyHistoryResponse)
async def daily_line_history(
    line_id: Annotated[str, Query(min_length=1, examples=["victoria"])],
    day: Annotated[date, Query(alias="date")],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DailyHistoryResponse:
    return await get_daily_history(session=session, line_id=line_id, day=day)
