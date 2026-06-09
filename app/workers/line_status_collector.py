import asyncio
import logging
import sys
from datetime import UTC, datetime

from app.clients.tfl import TflClient
from app.config import get_settings
from app.database import create_tables, session_factory
from app.line_status.models import LineStatusSnapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def collect_once(client: TflClient) -> int:
    observed_at = datetime.now(UTC)
    statuses = await client.get_rail_line_statuses()

    async with session_factory() as session:
        session.add_all(
            LineStatusSnapshot(
                line_id=status.line_id,
                line_name=status.line_name,
                mode_name=status.mode_name,
                status_severity=status.status_severity,
                status_description=status.status_description,
                reason=status.reason,
                observed_at=observed_at,
            )
            for status in statuses
        )
        await session.commit()

    return len(statuses)


async def run(*, once: bool = False) -> None:
    settings = get_settings()
    await create_tables()
    client = TflClient(settings.tfl_api_key)

    try:
        while True:
            try:
                count = await collect_once(client)
                logger.info("Stored %s line status snapshots", count)
            except Exception:
                logger.exception("TfL status collection failed")
                if once:
                    raise
            if once:
                return
            await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run(once="--once" in sys.argv[1:]))
