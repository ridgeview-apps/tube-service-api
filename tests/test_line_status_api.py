from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.security import require_api_key
from app.database import Base, get_session
from app.line_status.cache import daily_disruption_summary_cache, daily_timeline_cache
from app.line_status.lines import SUPPORTED_LINE_IDS
from app.line_status.models import LineStatus, LineStatusSnapshot
from app.line_status.time import current_operational_day, operational_day_bounds_london
from app.main import app

test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    poolclass=StaticPool,
)
db_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


async def get_test_session():
    async with db_session_factory() as session:
        yield session


async def bypass_api_key() -> None:
    pass


@pytest.fixture(autouse=True)
async def clean_database():
    daily_timeline_cache.clear()
    daily_disruption_summary_cache.clear()
    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[require_api_key] = bypass_api_key
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
                    observed_at=datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=6,
                            status_description="Severe Delays",
                            reason="Test disruption",
                            disruption_category="RealTime",
                            additional_info="Tickets accepted on local buses",
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="victoria",
                    observed_at=datetime(2026, 6, 9, 9, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=6,
                            status_description="Severe Delays",
                            reason="Test disruption",
                            disruption_category="RealTime",
                            additional_info="Tickets accepted on local buses",
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
                LineStatusSnapshot(
                    line_id="victoria",
                    observed_at=datetime(2026, 6, 10, 2, 59, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=9,
                            status_description="Minor Delays",
                            reason="Late-night disruption",
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="victoria",
                    observed_at=datetime(2026, 6, 10, 3, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=6,
                            status_description="Severe Delays",
                            reason="Next operational day",
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
            "/v1/line-status/timeline",
            params={"line_id": "victoria", "date": date(2026, 6, 9).isoformat()},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-06-09"
    assert body["starts_at"] == "2026-06-09T04:00:00+01:00"
    assert body["ends_at"] == "2026-06-10T04:00:00+01:00"
    assert len(body["snapshots"]) == 4
    assert [snapshot["observed_at"] for snapshot in body["snapshots"]] == [
        "2026-06-10T02:59:00Z",
        "2026-06-09T10:00:00Z",
        "2026-06-09T08:00:00Z",
        "2026-06-09T07:00:00Z",
    ]
    assert body["snapshots"][0]["statuses"][0]["status_severity_description"] == "Minor Delays"
    assert body["snapshots"][1]["statuses"][0]["status_severity_description"] == "Good Service"
    assert body["snapshots"][2]["statuses"][0] == {
        "status_severity": 6,
        "status_severity_description": "Severe Delays",
        "reason": "Test disruption",
        "disruption": {
            "category": "RealTime",
            "additional_info": "Tickets accepted on local buses",
        },
    }
    assert body["snapshots"][3]["statuses"][0]["status_severity_description"] == "Good Service"
    assert body["snapshots"][3]["statuses"][0]["disruption"] is None
    assert all(
        status["status_severity"] <= 10
        for snapshot in body["snapshots"]
        for status in snapshot["statuses"]
    )
    assert all(snapshot["observed_at"].endswith("Z") for snapshot in body["snapshots"])
    assert all("line_name" not in snapshot for snapshot in body["snapshots"])
    assert all("mode_name" not in snapshot for snapshot in body["snapshots"])


async def test_timeline_defaults_to_current_operational_day() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/line-status/timeline",
            params={"line_id": "victoria"},
        )

    assert response.status_code == 200
    assert response.json()["date"] == current_operational_day().isoformat()


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


async def test_timeline_ignores_unrelated_status_only_snapshots() -> None:
    async with db_session_factory() as session:
        session.add_all(
            [
                LineStatusSnapshot(
                    line_id="victoria",
                    observed_at=datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=6,
                            status_description="Severe Delays",
                            reason="Signal failure",
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="victoria",
                    observed_at=datetime(2026, 6, 9, 9, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=19,
                            status_description="Information",
                            reason="Station information",
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="victoria",
                    observed_at=datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
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
            "/v1/line-status/timeline",
            params={"line_id": "victoria", "date": date(2026, 6, 9).isoformat()},
        )

    assert response.status_code == 200
    snapshots = response.json()["snapshots"]
    assert [snapshot["statuses"][0]["status_severity_description"] for snapshot in snapshots] == [
        "Good Service",
        "Severe Delays",
    ]
    assert snapshots[1]["observed_at"].startswith("2026-06-09T08:00:00")


async def test_disruption_summary_reports_any_disruption_for_each_line() -> None:
    async with db_session_factory() as session:
        session.add_all(
            [
                LineStatusSnapshot(
                    line_id="circle",
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
                    line_id="circle",
                    observed_at=datetime(2026, 6, 9, 9, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=6,
                            status_description="Severe Delays",
                            reason="Later delays",
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="circle",
                    observed_at=datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
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
                    observed_at=datetime(2026, 6, 9, 11, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=9,
                            status_description="Minor Delays",
                            reason="New delays",
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="northern",
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
    body = response.json()
    assert body["date"] == "2026-06-09"
    assert body["timezone"] == "Europe/London"
    assert body["starts_at"] == "2026-06-09T04:00:00+01:00"
    assert body["ends_at"] == "2026-06-10T04:00:00+01:00"
    summary = body["lines"]
    assert set(summary) == SUPPORTED_LINE_IDS
    assert summary["circle"]["disrupted"] is True
    assert summary["circle"]["disruption_count"] == 2
    assert summary["circle"]["latest_disruption_at"] == "2026-06-09T11:00:00Z"
    assert summary["northern"]["disrupted"] is False
    assert summary["northern"]["disruption_count"] == 0
    assert summary["northern"]["latest_disruption_at"] is None
    assert all(
        not item["disrupted"]
        and item["disruption_count"] == 0
        and item["latest_disruption_at"] is None
        for line_id, item in summary.items()
        if line_id != "circle"
    )


async def test_disruption_summary_counts_special_service_as_disrupted() -> None:
    async with db_session_factory() as session:
        session.add(
            LineStatusSnapshot(
                line_id="district",
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
    summary = response.json()["lines"]
    assert set(summary) == SUPPORTED_LINE_IDS
    assert summary["district"]["disrupted"] is True
    assert summary["district"]["disruption_count"] == 1
    assert summary["district"]["latest_disruption_at"] == "2026-06-09T07:00:00Z"
    assert all(
        not item["disrupted"]
        and item["disruption_count"] == 0
        and item["latest_disruption_at"] is None
        for line_id, item in summary.items()
        if line_id != "district"
    )


async def test_planned_closure_is_in_timeline_but_not_disruption_summary() -> None:
    async with db_session_factory() as session:
        session.add(
            LineStatusSnapshot(
                line_id="district",
                observed_at=datetime(2026, 6, 9, 7, 0, tzinfo=UTC),
                statuses=[
                    LineStatus(
                        status_severity=4,
                        status_description="Planned Closure",
                        reason="Engineering works",
                    )
                ],
            )
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        timeline_response = await client.get(
            "/v1/line-status/timeline",
            params={"line_id": "district", "date": date(2026, 6, 9).isoformat()},
        )
        summary_response = await client.get(
            "/v1/line-status/disruption-summary",
            params={"date": date(2026, 6, 9).isoformat()},
        )

    assert timeline_response.status_code == 200
    assert timeline_response.json()["snapshots"][0]["statuses"][0] == {
        "status_severity": 4,
        "status_severity_description": "Planned Closure",
        "reason": "Engineering works",
        "disruption": None,
    }

    assert summary_response.status_code == 200
    summary = summary_response.json()["lines"]
    assert summary["district"] == {
        "disrupted": False,
        "disruption_count": 0,
        "latest_disruption_at": None,
    }


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
    today = current_operational_day()
    starts_at, ends_at = operational_day_bounds_london(today)
    assert today_response.json() == {
        "date": today.isoformat(),
        "timezone": "Europe/London",
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "lines": {
            line_id: {
                "disrupted": False,
                "disruption_count": 0,
                "latest_disruption_at": None,
            }
            for line_id in sorted(SUPPORTED_LINE_IDS)
        },
    }
    assert future_response.status_code == 422
    assert future_response.json() == {"detail": "Date cannot be in the future"}
