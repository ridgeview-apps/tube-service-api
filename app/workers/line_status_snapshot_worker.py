import asyncio
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.tfl import TflClient, TflLine, TflLineStatus
from app.config import get_settings
from app.database import session_factory as default_session_factory
from app.line_status.lines import SUPPORTED_LINE_IDS
from app.line_status.models import LineStatus, LineStatusSnapshot
from app.line_status.repository import (
    get_latest_snapshots_before,
    get_latest_snapshots_by_line,
)
from app.line_status.time import operational_day_bounds_utc, operational_day_for
from app.notifications.events import detect_notification_candidate
from app.notifications.matching import matching_delivery_targets
from app.notifications.repository import (
    create_pending_deliveries,
    get_notification_devices_with_preferences,
    get_or_create_notification_event,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


type _StatusValue = tuple[int, str, str | None, str | None, str | None]
type _NotificationSnapshotPair = tuple[LineStatusSnapshot | None, LineStatusSnapshot]


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def run(*, once: bool = False) -> None:
    settings = get_settings()
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
    observed_at = now().replace(microsecond=0)
    remote_lines = await tfl_client.get_rail_line_statuses()
    operational_date = operational_day_for(observed_at)
    day_start_utc, next_day_start_utc = operational_day_bounds_utc(operational_date)

    async with session_factory() as session:
        remote_lines_by_id = {line.id: line for line in remote_lines}
        missing_remote_line_ids = sorted(SUPPORTED_LINE_IDS - set(remote_lines_by_id))
        unsupported_remote_line_ids = sorted(set(remote_lines_by_id) - SUPPORTED_LINE_IDS)
        logger.info(
            "Fetched %s TfL line statuses for operational date %s",
            len(remote_lines_by_id),
            operational_date,
        )
        if missing_remote_line_ids:
            logger.warning(
                "TfL response missing %s supported lines: %s",
                len(missing_remote_line_ids),
                ", ".join(missing_remote_line_ids),
            )
        if unsupported_remote_line_ids:
            logger.warning(
                "TfL response included %s unsupported lines: %s",
                len(unsupported_remote_line_ids),
                ", ".join(unsupported_remote_line_ids),
            )

        line_ids_to_check = sorted(SUPPORTED_LINE_IDS | set(remote_lines_by_id))
        latest_snapshots_by_line = await get_latest_snapshots_by_line(
            session=session,
            line_ids=line_ids_to_check,
            start=day_start_utc,
            end=next_day_start_utc,
        )
        snapshots_to_store: list[LineStatusSnapshot] = []
        notification_snapshot_pairs: list[_NotificationSnapshotPair] = []

        for remote_line in remote_lines:
            latest_local_snapshot = latest_snapshots_by_line.get(remote_line.id)
            if _snapshot_changed(remote_line, latest_local_snapshot):
                snapshot = _create_snapshot(remote_line, observed_at)
                snapshots_to_store.append(snapshot)
                notification_snapshot_pairs.append((latest_local_snapshot, snapshot))

        missing_baseline_line_ids = sorted(
            set(missing_remote_line_ids) - set(latest_snapshots_by_line)
        )
        previous_snapshots_by_line = await get_latest_snapshots_before(
            session=session,
            line_ids=missing_baseline_line_ids,
            before=day_start_utc,
        )
        carried_forward_line_ids = sorted(previous_snapshots_by_line)
        if carried_forward_line_ids:
            logger.warning(
                "Carrying forward %s missing operational-day baselines: %s",
                len(carried_forward_line_ids),
                ", ".join(carried_forward_line_ids),
            )
        snapshots_to_store.extend(
            _copy_snapshot(snapshot, observed_at)
            for snapshot in previous_snapshots_by_line.values()
        )

        session.add_all(snapshots_to_store)
        await session.commit()
        await _create_pending_notification_deliveries(
            session=session,
            snapshot_pairs=notification_snapshot_pairs,
        )

    return len(snapshots_to_store)


async def _create_pending_notification_deliveries(
    *,
    session: AsyncSession,
    snapshot_pairs: list[_NotificationSnapshotPair],
) -> int:
    devices = await get_notification_devices_with_preferences(session)
    delivery_count = 0

    for previous_snapshot, current_snapshot in snapshot_pairs:
        candidate = detect_notification_candidate(
            previous_snapshot=previous_snapshot,
            current_snapshot=current_snapshot,
        )
        if candidate is None:
            continue

        event, _ = await get_or_create_notification_event(session, candidate)
        targets = matching_delivery_targets(
            candidate=candidate,
            devices=devices,
            now=current_snapshot.observed_at,
        )
        deliveries = await create_pending_deliveries(session, event, targets)
        delivery_count += len(deliveries)

    return delivery_count


def _snapshot_changed(
    remote_line: TflLine,
    local_snapshot: LineStatusSnapshot | None,
) -> bool:
    if local_snapshot is None:
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


def _copy_snapshot(
    snapshot: LineStatusSnapshot,
    observed_at: datetime,
) -> LineStatusSnapshot:
    return LineStatusSnapshot(
        line_id=snapshot.line_id,
        observed_at=observed_at,
        statuses=[
            LineStatus(
                status_severity=status.status_severity,
                status_description=status.status_description,
                reason=status.reason,
                disruption_category=status.disruption_category,
                additional_info=status.additional_info,
            )
            for status in snapshot.statuses
        ],
    )


if __name__ == "__main__":
    asyncio.run(run(once="--once" in sys.argv[1:]))
