from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_api_key
from app.database import get_session
from app.line_status.schemas import DailyDisruptionSummaryRead, DailyTimelineRead
from app.line_status.service import get_daily_disruption_summary, get_daily_timeline
from app.line_status.time import current_operational_day

router = APIRouter(
    prefix="/v1/line-status",
    tags=["line status"],
    dependencies=[Depends(require_api_key)],
)


def _requested_day_or_today(day: date | None) -> date:
    current_day = current_operational_day()
    requested_day = day or current_day
    if requested_day > current_day:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Date cannot be in the future",
        )
    return requested_day


@router.get("/timeline", response_model=DailyTimelineRead)
async def daily_line_timeline(
    line_id: Annotated[str, Query(min_length=1, examples=["victoria"])],
    session: Annotated[AsyncSession, Depends(get_session)],
    day: Annotated[
        date | None,
        Query(
            alias="date",
            description="London operational date (04:00-04:00); defaults to current",
        ),
    ] = None,
) -> DailyTimelineRead:
    return await get_daily_timeline(
        session=session,
        line_id=line_id,
        day=_requested_day_or_today(day),
    )


@router.get("/disruption-summary", response_model=DailyDisruptionSummaryRead)
async def daily_line_disruption_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    day: Annotated[
        date | None,
        Query(
            alias="date",
            description="London operational date (04:00-04:00); defaults to current",
        ),
    ] = None,
) -> DailyDisruptionSummaryRead:
    return await get_daily_disruption_summary(
        session=session,
        day=_requested_day_or_today(day),
    )
