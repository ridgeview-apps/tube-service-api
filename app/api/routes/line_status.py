from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.line_status.schemas import DailyHistoryRead
from app.line_status.service import get_daily_history
from app.line_status.time import today_in_london

router = APIRouter(prefix="/v1/line-status", tags=["line status"])


@router.get("/history", response_model=DailyHistoryRead)
async def daily_line_history(
    line_id: Annotated[str, Query(min_length=1, examples=["victoria"])],
    session: Annotated[AsyncSession, Depends(get_session)],
    day: Annotated[
        date | None,
        Query(
            alias="date",
            description="London calendar date; defaults to today",
        ),
    ] = None,
) -> DailyHistoryRead:
    current_day = today_in_london()
    requested_day = day or current_day
    if requested_day > current_day:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Date cannot be in the future",
        )

    return await get_daily_history(
        session=session,
        line_id=line_id,
        day=requested_day,
    )
