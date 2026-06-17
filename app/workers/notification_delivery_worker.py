import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.database import session_factory as default_session_factory
from app.notifications.sender import NoopPushSender, PushSender, process_pending_deliveries

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run(*, once: bool = False) -> None:
    settings = get_settings()
    sender = NoopPushSender()

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
    async with session_factory() as session:
        return await process_pending_deliveries(
            session=session,
            sender=sender,
            limit=limit,
        )


if __name__ == "__main__":
    asyncio.run(run(once="--once" in sys.argv[1:]))
