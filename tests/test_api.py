from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.line_status.models import LineStatus, LineStatusSnapshot
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
    app.dependency_overrides[get_session] = get_test_session
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    app.dependency_overrides.clear()


async def test_health() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_history_returns_only_requested_london_day() -> None:
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
                    observed_at=datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=6,
                            status_description="Severe Delays",
                            reason="Test disruption",
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
            "/v1/line-status/history",
            params={"line_id": "victoria", "date": date(2026, 6, 9).isoformat()},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-06-09"
    assert len(body["snapshots"]) == 1
    assert body["snapshots"][0]["statuses"][0]["status_description"] == "Severe Delays"
    assert body["snapshots"][0]["observed_at"].endswith("Z")
