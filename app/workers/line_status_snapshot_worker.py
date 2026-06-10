import asyncio
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.tfl import TflClient, TflLine, TflLineStatus
from app.config import get_settings
from app.database import create_tables
from app.database import session_factory as default_session_factory
from app.line_status.models import LineStatus, LineStatusSnapshot
from app.line_status.repository import get_latest_snapshots_by_line
from app.line_status.time import LONDON, london_day_bounds_utc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


type _StatusValue = tuple[int, str, str | None, str | None, str | None]


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def run(*, once: bool = False) -> None:
    settings = get_settings()
    await create_tables()
    tfl_client = TflClient(settings.tfl_api_key)

    try:
        while True:
            try:
                stored_snapshot_count = await capture_snapshots_once(tfl_client)
                logger.info("Stored %s line status snapshots", stored_snapshot_count)
            except Exception:
                logger.exception("TfL status collection failed")
                if once:
                    raise
            if once:
                return
            await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        await tfl_client.close()


async def capture_snapshots_once(
    tfl_client: TflClient,
    *,
    session_factory: async_sessionmaker[AsyncSession] = default_session_factory,
    now: Callable[[], datetime] = _utc_now,
) -> int:
    observed_at = now()
    remote_lines = await tfl_client.get_rail_line_statuses()
    today_in_london = observed_at.astimezone(LONDON).date()
    today_start_utc, tomorrow_start_utc = london_day_bounds_utc(today_in_london)

    async with session_factory() as session:
        latest_snapshots_by_line = await get_latest_snapshots_by_line(
            session=session,
            line_ids=[line.id for line in remote_lines],
            start=today_start_utc,
            end=tomorrow_start_utc,
        )
        snapshots_to_store: list[LineStatusSnapshot] = []

        for remote_line in remote_lines:
            latest_local_snapshot = latest_snapshots_by_line.get(remote_line.id)
            if _snapshot_changed(remote_line, latest_local_snapshot):
                snapshots_to_store.append(_create_snapshot(remote_line, observed_at))

        session.add_all(snapshots_to_store)
        await session.commit()

    return len(snapshots_to_store)


def _snapshot_changed(
    remote_line: TflLine,
    local_snapshot: LineStatusSnapshot | None,
) -> bool:
    if local_snapshot is None:
        return True

    if (
        remote_line.name != local_snapshot.line_name
        or remote_line.mode_name != local_snapshot.mode_name
    ):
        return True

    remote_statuses = sorted(
        (_status_value(status) for status in remote_line.statuses),
        key=_status_sort_key,
    )
    local_statuses = sorted(
        (_status_value(status) for status in local_snapshot.statuses),
        key=_status_sort_key,
    )
    return remote_statuses != local_statuses


def _status_value(status: TflLineStatus | LineStatus) -> _StatusValue:
    return (
        status.status_severity,
        status.status_description,
        status.reason,
        status.disruption_category,
        status.additional_info,
    )


def _status_sort_key(status: _StatusValue) -> tuple[int, str, str, str, str]:
    severity, description, reason, disruption_category, additional_info = status
    return (
        severity,
        description,
        reason or "",
        disruption_category or "",
        additional_info or "",
    )


def _create_snapshot(
    line: TflLine,
    observed_at: datetime,
) -> LineStatusSnapshot:
    return LineStatusSnapshot(
        line_id=line.id,
        line_name=line.name,
        mode_name=line.mode_name,
        observed_at=observed_at,
        statuses=[
            LineStatus(
                status_severity=status.status_severity,
                status_description=status.status_description,
                reason=status.reason,
                disruption_category=status.disruption_category,
                additional_info=status.additional_info,
            )
            for status in line.statuses
        ],
    )


if __name__ == "__main__":
    asyncio.run(run(once="--once" in sys.argv[1:]))
