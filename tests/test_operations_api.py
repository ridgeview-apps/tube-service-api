from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.security import require_api_key
from app.database import Base, get_session
from app.main import app
from app.operations.models import WorkerRun

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
    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[require_api_key] = bypass_api_key
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    app.dependency_overrides.clear()


async def test_worker_runs_returns_latest_run_per_worker() -> None:
    async with db_session_factory() as session:
        session.add_all(
            [
                WorkerRun(
                    worker_name="line_status_snapshot_worker",
                    started_at=datetime(2026, 6, 16, 8, 0, tzinfo=UTC),
                    finished_at=datetime(2026, 6, 16, 8, 1, tzinfo=UTC),
                    status="failed",
                    processed_count=0,
                    error_message="Old failure",
                ),
                WorkerRun(
                    worker_name="line_status_snapshot_worker",
                    started_at=datetime(2026, 6, 16, 8, 10, 0, 123456, tzinfo=UTC),
                    finished_at=datetime(2026, 6, 16, 8, 11, 0, 234567, tzinfo=UTC),
                    status="success",
                    processed_count=2,
                    error_message=None,
                ),
                WorkerRun(
                    worker_name="notification_delivery_worker",
                    started_at=datetime(2026, 6, 16, 8, 12, 0, 345678, tzinfo=UTC),
                    finished_at=datetime(2026, 6, 16, 8, 13, 0, 456789, tzinfo=UTC),
                    status="success",
                    processed_count=5,
                    error_message=None,
                ),
            ]
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/operations/workers")

    assert response.status_code == 200
    assert response.json() == {
        "workers": {
            "line_status_snapshot_worker": {
                "worker_name": "line_status_snapshot_worker",
                "started_at": "2026-06-16T08:10:00Z",
                "finished_at": "2026-06-16T08:11:00Z",
                "status": "success",
                "processed_count": 2,
                "error_message": None,
            },
            "notification_delivery_worker": {
                "worker_name": "notification_delivery_worker",
                "started_at": "2026-06-16T08:12:00Z",
                "finished_at": "2026-06-16T08:13:00Z",
                "status": "success",
                "processed_count": 5,
                "error_message": None,
            },
        }
    }


async def test_worker_runs_returns_empty_response_without_worker_runs() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/operations/workers")

    assert response.status_code == 200
    assert response.json() == {"workers": {}}
