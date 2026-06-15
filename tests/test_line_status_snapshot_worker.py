from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.clients.tfl import TflLine, TflLineStatus
from app.database import Base
from app.line_status.models import LineStatus, LineStatusSnapshot
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
