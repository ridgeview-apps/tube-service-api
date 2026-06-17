from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.operations.models import WorkerRun

WORKER_RUN_SUCCESS_STATUS = "success"
WORKER_RUN_FAILED_STATUS = "failed"


def utc_now() -> datetime:
    return datetime.now(UTC)


async def record_worker_run(
    session: AsyncSession,
    *,
    worker_name: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    processed_count: int,
    error_message: str | None = None,
) -> WorkerRun:
    worker_run = WorkerRun(
        worker_name=worker_name,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        processed_count=processed_count,
        error_message=error_message,
    )
    session.add(worker_run)
    await session.commit()
    await session.refresh(worker_run)
    return worker_run


async def record_worker_success(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    worker_name: str,
    started_at: datetime,
    processed_count: int,
) -> WorkerRun:
    async with session_factory() as session:
        return await record_worker_run(
            session,
            worker_name=worker_name,
            started_at=started_at,
            finished_at=utc_now(),
            status=WORKER_RUN_SUCCESS_STATUS,
            processed_count=processed_count,
        )


async def record_worker_failure(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    worker_name: str,
    started_at: datetime,
    error: Exception,
) -> WorkerRun:
    async with session_factory() as session:
        return await record_worker_run(
            session,
            worker_name=worker_name,
            started_at=started_at,
            finished_at=utc_now(),
            status=WORKER_RUN_FAILED_STATUS,
            processed_count=0,
            error_message=str(error),
        )


async def get_latest_worker_runs(session: AsyncSession) -> dict[str, WorkerRun]:
    worker_runs = (
        await session.scalars(select(WorkerRun).order_by(WorkerRun.finished_at.desc()))
    ).all()
    latest_runs: dict[str, WorkerRun] = {}
    for worker_run in worker_runs:
        latest_runs.setdefault(worker_run.worker_name, worker_run)
    return latest_runs
