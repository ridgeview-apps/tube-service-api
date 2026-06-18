from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.line_status.models import LineStatusSnapshot


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


async def get_latest_snapshots_before(
    session: AsyncSession,
    line_ids: list[str],
    before: datetime,
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
            LineStatusSnapshot.observed_at < before,
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


async def get_line_histories(
    session: AsyncSession,
    start: datetime,
    end: datetime,
) -> dict[str, list[LineStatusSnapshot]]:
    statement = (
        select(LineStatusSnapshot)
        .where(
            LineStatusSnapshot.observed_at >= start,
            LineStatusSnapshot.observed_at < end,
        )
        .options(selectinload(LineStatusSnapshot.statuses))
        .order_by(LineStatusSnapshot.line_id, LineStatusSnapshot.observed_at.desc())
    )
    histories: dict[str, list[LineStatusSnapshot]] = {}
    for snapshot in (await session.scalars(statement)).all():
        histories.setdefault(snapshot.line_id, []).append(snapshot)
    return histories
