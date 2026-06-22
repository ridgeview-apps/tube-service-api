from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.clients.tfl import TflLine, TflLineStatus
from app.database import Base
from app.line_status.models import LineStatus, LineStatusSnapshot
from app.notifications.models import (
    NotificationDelivery,
    NotificationDevice,
    NotificationEvent,
    NotificationLinePreference,
    NotificationPreferences,
)
from app.notifications.repository import PENDING_DELIVERY_STATUS
from app.operations.models import WorkerRun
from app.workers.line_status_snapshot_worker import capture_snapshots_once

test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    poolclass=StaticPool,
)
db_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


class FakeTflClient:
    def __init__(self, lines: list[TflLine]) -> None:
        self.lines = lines

    async def get_rail_line_statuses(self) -> list[TflLine]:
        return self.lines


class FailingTflClient:
    async def get_rail_line_statuses(self) -> list[TflLine]:
        raise RuntimeError("TfL is unavailable")


def line(
    line_id: str,
    description: str = "Good Service",
    reason: str | None = None,
    disruption_category: str | None = None,
    additional_info: str | None = None,
) -> TflLine:
    return TflLine(
        id=line_id,
        name=line_id.title(),
        mode_name="tube",
        statuses=[
            TflLineStatus(
                status_severity=10 if description == "Good Service" else 6,
                status_description=description,
                reason=reason,
                disruption_category=disruption_category,
                additional_info=additional_info,
            )
        ],
    )


@pytest.fixture(autouse=True)
async def clean_database():
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


async def stored_snapshot_count() -> int:
    async with db_session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(LineStatusSnapshot))
    return count or 0


async def stored_status_count() -> int:
    async with db_session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(LineStatus))
    return count or 0


async def latest_stored_status() -> LineStatus:
    async with db_session_factory() as session:
        return await session.scalar(select(LineStatus).order_by(LineStatus.id.desc()))


async def latest_stored_snapshot() -> LineStatusSnapshot:
    async with db_session_factory() as session:
        return await session.scalar(
            select(LineStatusSnapshot).order_by(LineStatusSnapshot.id.desc())
        )


async def stored_snapshots() -> list[LineStatusSnapshot]:
    async with db_session_factory() as session:
        return list(
            await session.scalars(
                select(LineStatusSnapshot).order_by(
                    LineStatusSnapshot.observed_at,
                    LineStatusSnapshot.line_id,
                )
            )
        )


async def stored_notification_events() -> list[NotificationEvent]:
    async with db_session_factory() as session:
        return list(await session.scalars(select(NotificationEvent).order_by(NotificationEvent.id)))


async def stored_notification_deliveries() -> list[NotificationDelivery]:
    async with db_session_factory() as session:
        return list(
            await session.scalars(select(NotificationDelivery).order_by(NotificationDelivery.id))
        )


async def stored_worker_runs() -> list[WorkerRun]:
    async with db_session_factory() as session:
        return list(await session.scalars(select(WorkerRun).order_by(WorkerRun.id)))


async def add_notification_device(
    *,
    device_id: str = "install-123",
    line_ids: list[str] | None = None,
    schedule_preset: str = "anytime",
) -> None:
    now = datetime(2026, 6, 9, 7, 0, tzinfo=UTC)
    async with db_session_factory() as session:
        session.add(
            NotificationDevice(
                device_id=device_id,
                platform="ios",
                push_token=f"{device_id}-token",
                enabled=True,
                app_version=None,
                created_at=now,
                updated_at=now,
                last_seen_at=now,
                preferences=NotificationPreferences(
                    device_id=device_id,
                    timezone="Europe/London",
                    created_at=now,
                    updated_at=now,
                    lines=[
                        NotificationLinePreference(
                            device_id=device_id,
                            line_id=line_id,
                            enabled=True,
                            severity_threshold="minor_delays",
                            notify_recoveries=True,
                            schedule_preset=schedule_preset,
                            custom_schedules=[],
                        )
                        for line_id in (line_ids or ["victoria"])
                    ],
                ),
            )
        )
        await session.commit()


async def test_observed_at_is_stored_at_second_precision() -> None:
    client = FakeTflClient([line("victoria")])

    await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 0, 30, 123456, tzinfo=UTC),
    )

    snapshot = await latest_stored_snapshot()
    assert snapshot.observed_at == datetime(2026, 6, 9, 8, 0, 30)


async def test_capture_snapshots_once_only_stores_changed_lines() -> None:
    client = FakeTflClient([line("victoria"), line("central")])

    first_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
    )
    unchanged_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 10, tzinfo=UTC),
    )

    client.lines = [
        line("victoria", "Severe Delays", "Test disruption"),
        line("central"),
    ]
    changed_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 20, tzinfo=UTC),
    )

    assert first_count == 2
    assert unchanged_count == 0
    assert changed_count == 1
    assert await stored_snapshot_count() == 3
    assert await stored_status_count() == 3


async def test_capture_snapshots_once_records_successful_worker_run() -> None:
    client = FakeTflClient([line("victoria")])

    await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
    )

    [worker_run] = await stored_worker_runs()
    assert worker_run.worker_name == "line_status_snapshot_worker"
    assert worker_run.status == "success"
    assert worker_run.processed_count == 1
    assert worker_run.error_message is None


async def test_capture_snapshots_once_records_failed_worker_run() -> None:
    with pytest.raises(RuntimeError, match="TfL is unavailable"):
        await capture_snapshots_once(
            FailingTflClient(),
            session_factory=db_session_factory,
            now=lambda: datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
        )

    [worker_run] = await stored_worker_runs()
    assert worker_run.worker_name == "line_status_snapshot_worker"
    assert worker_run.status == "failed"
    assert worker_run.processed_count == 0
    assert worker_run.error_message == "TfL is unavailable"


async def test_status_order_does_not_count_as_a_change() -> None:
    district = TflLine(
        id="district",
        name="District",
        mode_name="tube",
        statuses=[
            TflLineStatus(
                status_severity=6,
                status_description="Part Closure",
                reason="First",
            ),
            TflLineStatus(
                status_severity=6,
                status_description="Severe Delays",
                reason="Second",
            ),
        ],
    )
    client = FakeTflClient([district])

    first_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
    )
    district.statuses.reverse()
    reordered_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
    )

    assert first_count == 1
    assert reordered_count == 0
    assert await stored_snapshot_count() == 1
    assert await stored_status_count() == 2


async def test_disruption_details_count_as_a_change_and_are_stored() -> None:
    client = FakeTflClient(
        [
            line(
                "victoria",
                "Severe Delays",
                "Signal failure",
                disruption_category="RealTime",
                additional_info="Tickets accepted on buses",
            )
        ]
    )

    first_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
    )
    client.lines = [
        line(
            "victoria",
            "Severe Delays",
            "Signal failure",
            disruption_category="RealTime",
            additional_info="Tickets accepted on buses and National Rail",
        )
    ]
    changed_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
    )

    stored_status = await latest_stored_status()
    assert first_count == 1
    assert changed_count == 1
    assert stored_status.disruption_category == "RealTime"
    assert stored_status.additional_info == "Tickets accepted on buses and National Rail"


async def test_first_collection_of_new_operational_day_stores_baseline() -> None:
    client = FakeTflClient([line("victoria")])

    previous_day_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 2, 50, tzinfo=UTC),
    )
    new_day_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 3, 10, tzinfo=UTC),
    )
    unchanged_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 3, 20, tzinfo=UTC),
    )

    assert previous_day_count == 1
    assert new_day_count == 1
    assert unchanged_count == 0
    assert await stored_snapshot_count() == 2


async def test_first_collection_of_new_operational_day_carries_forward_missing_lines() -> None:
    client = FakeTflClient([line("victoria"), line("central")])

    previous_day_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 2, 50, tzinfo=UTC),
    )
    client.lines = [line("victoria")]
    new_day_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 3, 10, tzinfo=UTC),
    )

    snapshots = await stored_snapshots()
    current_day_snapshots = [
        snapshot for snapshot in snapshots if snapshot.observed_at == datetime(2026, 6, 9, 3, 10)
    ]
    current_day_lines = {snapshot.line_id for snapshot in current_day_snapshots}

    assert previous_day_count == 2
    assert new_day_count == 2
    assert current_day_lines == {"central", "victoria"}
    assert (
        next(snapshot for snapshot in current_day_snapshots if snapshot.line_id == "central")
        .statuses[0]
        .status_description
        == "Good Service"
    )


async def test_capture_snapshots_creates_pending_notification_delivery_for_disruption() -> None:
    await add_notification_device()
    client = FakeTflClient([line("victoria")])

    baseline_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
    )
    client.lines = [line("victoria", "Severe Delays", "Signal failure")]
    disruption_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 10, tzinfo=UTC),
    )

    events = await stored_notification_events()
    deliveries = await stored_notification_deliveries()

    assert baseline_count == 1
    assert disruption_count == 1
    assert len(events) == 1
    assert events[0].line_id == "victoria"
    assert events[0].event_type == "disruption_started"
    assert events[0].severity == 6
    assert events[0].status_description == "Severe Delays"
    assert events[0].reason == "Signal failure"
    assert len(deliveries) == 1
    assert deliveries[0].event_id == events[0].id
    assert deliveries[0].device_id == "install-123"
    assert deliveries[0].push_token == "install-123-token"
    assert deliveries[0].status == PENDING_DELIVERY_STATUS


async def test_capture_snapshots_does_not_create_delivery_for_unmatched_preferences() -> None:
    await add_notification_device(line_ids=["central"])
    client = FakeTflClient([line("victoria")])

    await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
    )
    client.lines = [line("victoria", "Severe Delays", "Signal failure")]
    await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 10, tzinfo=UTC),
    )

    events = await stored_notification_events()
    deliveries = await stored_notification_deliveries()

    assert len(events) == 1
    assert deliveries == []


async def test_capture_snapshots_does_not_duplicate_delivery_for_unchanged_disruption() -> None:
    await add_notification_device()
    client = FakeTflClient([line("victoria")])

    await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
    )
    client.lines = [line("victoria", "Severe Delays", "Signal failure")]
    await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 10, tzinfo=UTC),
    )
    unchanged_count = await capture_snapshots_once(
        client,
        session_factory=db_session_factory,
        now=lambda: datetime(2026, 6, 9, 8, 20, tzinfo=UTC),
    )

    assert unchanged_count == 0
    assert len(await stored_notification_events()) == 1
    assert len(await stored_notification_deliveries()) == 1
