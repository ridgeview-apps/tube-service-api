from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.line_status.schemas import DailyHistoryRead, LineDisruptionSummaryRead
from app.line_status.service import get_daily_disruption_summary, get_daily_history
from app.line_status.time import today_in_london

router = APIRouter(prefix="/v1/line-status", tags=["line status"])


def _requested_day_or_today(day: date | None) -> date:
    current_day = today_in_london()
    requested_day = day or current_day
    if requested_day > current_day:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Date cannot be in the future",
        )
    return requested_day


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
    return await get_daily_history(
        session=session,
        line_id=line_id,
        day=_requested_day_or_today(day),
    )


@router.get("/disruption-summary", response_model=list[LineDisruptionSummaryRead])
async def daily_line_disruption_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    day: Annotated[
        date | None,
        Query(
            alias="date",
            description="London calendar date; defaults to today",
        ),
    ] = None,
) -> list[LineDisruptionSummaryRead]:
    return await get_daily_disruption_summary(
        session=session,
        day=_requested_day_or_today(day),
    )
