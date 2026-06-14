from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.line_status.models import LineStatus, LineStatusSnapshot
from app.line_status.severity import DISRUPTION_SEVERITIES


async def get_latest_snapshots_by_line(
    session: AsyncSession,
    line_ids: list[str],
    start: datetime,
    end: datetime,
) -> dict[str, LineStatusSnapshot]:
    if not line_ids:
        return {}

    latest_snapshots = (
        select(
            LineStatusSnapshot.line_id,
            func.max(LineStatusSnapshot.observed_at).label("observed_at"),
        )
        .where(
            LineStatusSnapshot.line_id.in_(line_ids),
            LineStatusSnapshot.observed_at >= start,
            LineStatusSnapshot.observed_at < end,
        )
        .group_by(LineStatusSnapshot.line_id)
        .subquery()
    )

    statement = (
        select(LineStatusSnapshot)
        .join(
            latest_snapshots,
            and_(
                LineStatusSnapshot.line_id == latest_snapshots.c.line_id,
                LineStatusSnapshot.observed_at == latest_snapshots.c.observed_at,
            ),
        )
        .options(selectinload(LineStatusSnapshot.statuses))
    )

    snapshots = (await session.scalars(statement)).all()
    return {snapshot.line_id: snapshot for snapshot in snapshots}


async def get_line_history(
    session: AsyncSession,
    line_id: str,
    start: datetime,
    end: datetime,
) -> list[LineStatusSnapshot]:
    statement = (
        select(LineStatusSnapshot)
        .where(
            LineStatusSnapshot.line_id == line_id,
            LineStatusSnapshot.observed_at >= start,
            LineStatusSnapshot.observed_at < end,
        )
        .options(selectinload(LineStatusSnapshot.statuses))
        .order_by(LineStatusSnapshot.observed_at.desc())
    )
    return list((await session.scalars(statement)).all())


async def get_disruption_summary(
    session: AsyncSession,
    start: datetime,
    end: datetime,
) -> dict[str, tuple[int, datetime | None]]:
    snapshot_disrupted = func.max(
        case(
            (LineStatus.status_severity.in_(tuple(DISRUPTION_SEVERITIES)), 1),
            else_=0,
        )
    ).label("disrupted")
    snapshots = (
        select(
            LineStatusSnapshot.line_id,
            LineStatusSnapshot.observed_at,
            snapshot_disrupted,
        )
        .outerjoin(LineStatus, LineStatus.snapshot_id == LineStatusSnapshot.id)
        .where(
            LineStatusSnapshot.observed_at >= start,
            LineStatusSnapshot.observed_at < end,
        )
        .group_by(
            LineStatusSnapshot.id,
            LineStatusSnapshot.line_id,
            LineStatusSnapshot.observed_at,
        )
        .subquery()
    )
    previous_disrupted = func.lag(snapshots.c.disrupted).over(
        partition_by=snapshots.c.line_id,
        order_by=snapshots.c.observed_at,
    )
    transitions = select(
        snapshots.c.line_id,
        snapshots.c.observed_at,
        snapshots.c.disrupted,
        previous_disrupted.label("previous_disrupted"),
    ).subquery()
    disruption_started = case(
        (
            (transitions.c.disrupted == 1)
            & (func.coalesce(transitions.c.previous_disrupted, 0) == 0),
            1,
        ),
        else_=0,
    )
    latest_disruption_at = func.max(
        case(
            (transitions.c.disrupted == 1, transitions.c.observed_at),
            else_=None,
        )
    )
    statement = (
        select(
            transitions.c.line_id,
            func.sum(disruption_started).label("disruption_count"),
            latest_disruption_at.label("latest_disruption_at"),
        )
        .group_by(transitions.c.line_id)
        .order_by(transitions.c.line_id)
    )

    rows = (await session.execute(statement)).all()
    return {
        line_id: (disruption_count, latest_disruption_at)
        for line_id, disruption_count, latest_disruption_at in rows
    }
