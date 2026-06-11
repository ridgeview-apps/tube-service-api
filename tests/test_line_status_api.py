from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.line_status.cache import daily_disruption_summary_cache, daily_timeline_cache
from app.line_status.models import LineStatus, LineStatusSnapshot
from app.line_status.time import today_in_london
from app.main import app

test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    poolclass=StaticPool,
)
db_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


async def get_test_session():
    async with db_session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
async def clean_database():
    daily_timeline_cache.clear()
    daily_disruption_summary_cache.clear()
    app.dependency_overrides[get_session] = get_test_session
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    daily_timeline_cache.clear()
    daily_disruption_summary_cache.clear()
    app.dependency_overrides.clear()


async def test_timeline_returns_only_requested_london_day() -> None:
    async with db_session_factory() as session:
        session.add_all(
            [
                LineStatusSnapshot(
                    line_id="victoria",
                    line_name="Victoria",
                    mode_name="tube",
                    observed_at=datetime(2026, 6, 8, 22, 59, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=10,
                            status_description="Good Service",
                            reason=None,
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="victoria",
                    line_name="Victoria",
                    mode_name="tube",
                    observed_at=datetime(2026, 6, 9, 7, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=10,
                            status_description="Good Service",
                            reason=None,
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="victoria",
                    line_name="Victoria",
                    mode_name="tube",
                    observed_at=datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=6,
                            status_description="Severe Delays",
                            reason="Test disruption",
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="victoria",
                    line_name="Victoria",
                    mode_name="tube",
                    observed_at=datetime(2026, 6, 9, 9, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=6,
                            status_description="Severe Delays",
                            reason="Test disruption",
                        ),
                        LineStatus(
                            status_severity=13,
                            status_description="No Step Free Access",
                            reason="Lift unavailable",
                        ),
                    ],
                ),
                LineStatusSnapshot(
                    line_id="victoria",
                    line_name="Victoria",
                    mode_name="tube",
                    observed_at=datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=10,
                            status_description="Good Service",
                            reason=None,
                        ),
                        LineStatus(
                            status_severity=19,
                            status_description="Information",
                            reason="Station information",
                        ),
                    ],
                ),
            ]
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/line-status/timeline",
            params={"line_id": "victoria", "date": date(2026, 6, 9).isoformat()},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-06-09"
    assert len(body["snapshots"]) == 3
    assert body["snapshots"][0]["statuses"][0]["status_description"] == "Good Service"
    assert body["snapshots"][1]["statuses"][0]["status_description"] == "Severe Delays"
    assert body["snapshots"][2]["statuses"][0]["status_description"] == "Good Service"
    assert all(
        status["status_severity"] <= 10
        for snapshot in body["snapshots"]
        for status in snapshot["statuses"]
    )
    assert body["snapshots"][1]["observed_at"].startswith("2026-06-09T08:00:00")
    assert body["snapshots"][0]["observed_at"].endswith("Z")


async def test_timeline_defaults_to_today_in_london() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/line-status/timeline",
            params={"line_id": "victoria"},
        )

    assert response.status_code == 200
    assert response.json()["date"] == today_in_london().isoformat()


async def test_timeline_rejects_future_date() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/line-status/timeline",
            params={"line_id": "victoria", "date": "2999-01-01"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Date cannot be in the future"}


async def test_disruption_summary_reports_any_disruption_for_each_line() -> None:
    async with db_session_factory() as session:
        session.add_all(
            [
                LineStatusSnapshot(
                    line_id="circle",
                    line_name="Circle",
                    mode_name="tube",
                    observed_at=datetime(2026, 6, 9, 7, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=10,
                            status_description="Good Service",
                            reason=None,
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="circle",
                    line_name="Circle",
                    mode_name="tube",
                    observed_at=datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=9,
                            status_description="Minor Delays",
                            reason="Earlier delays",
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="northern",
                    line_name="Northern",
                    mode_name="tube",
                    observed_at=datetime(2026, 6, 9, 7, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=10,
                            status_description="Good Service",
                            reason=None,
                        )
                    ],
                ),
            ]
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/line-status/disruption-summary",
            params={"date": date(2026, 6, 9).isoformat()},
        )

    assert response.status_code == 200
    assert response.json() == [
        {"line_id": "circle", "disrupted": True},
        {"line_id": "northern", "disrupted": False},
    ]


async def test_disruption_summary_counts_special_service_as_disrupted() -> None:
    async with db_session_factory() as session:
        session.add(
            LineStatusSnapshot(
                line_id="district",
                line_name="District",
                mode_name="tube",
                observed_at=datetime(2026, 6, 9, 7, 0, tzinfo=UTC),
                statuses=[
                    LineStatus(
                        status_severity=0,
                        status_description="Special Service",
                        reason="Special timetable",
                    ),
                    LineStatus(
                        status_severity=10,
                        status_description="Good Service",
                        reason=None,
                    ),
                ],
            )
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/line-status/disruption-summary",
            params={"date": date(2026, 6, 9).isoformat()},
        )

    assert response.status_code == 200
    assert response.json() == [{"line_id": "district", "disrupted": True}]


async def test_disruption_summary_defaults_to_today_and_rejects_future_date() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        today_response = await client.get("/v1/line-status/disruption-summary")
        future_response = await client.get(
            "/v1/line-status/disruption-summary",
            params={"date": "2999-01-01"},
        )

    assert today_response.status_code == 200
    assert today_response.json() == []
    assert future_response.status_code == 422
    assert future_response.json() == {"detail": "Date cannot be in the future"}
