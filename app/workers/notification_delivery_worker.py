import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.database import session_factory as default_session_factory
from app.notifications.sender import (
    PushSender,
    build_configured_push_sender,
    process_pending_deliveries,
)
from app.operations.repository import (
    record_worker_failure,
    record_worker_success,
    utc_now,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
WORKER_NAME = "notification_delivery_worker"


async def run(*, once: bool = False) -> None:
    settings = get_settings()
    sender = build_configured_push_sender(settings)

    while True:
        try:
            processed_count = await process_pending_deliveries_once(
                sender=sender,
                limit=settings.notification_delivery_batch_size,
            )
            logger.info("Processed %s notification deliveries", processed_count)
        except Exception:
            logger.exception("Notification delivery processing failed")
            if once:
                raise
        if once:
            return
        await asyncio.sleep(settings.notification_delivery_poll_interval_seconds)


async def process_pending_deliveries_once(
    *,
    sender: PushSender,
    limit: int = 100,
    session_factory: async_sessionmaker[AsyncSession] = default_session_factory,
) -> int:
    started_at = utc_now()
    try:
        async with session_factory() as session:
            processed_count = await process_pending_deliveries(
                session=session,
                sender=sender,
                limit=limit,
            )
    except Exception as error:
        await record_worker_failure(
            session_factory=session_factory,
            worker_name=WORKER_NAME,
            started_at=started_at,
            error=error,
        )
        raise

    await record_worker_success(
        session_factory=session_factory,
        worker_name=WORKER_NAME,
        started_at=started_at,
        processed_count=processed_count,
    )
    return processed_count


if __name__ == "__main__":
    asyncio.run(run(once="--once" in sys.argv[1:]))
