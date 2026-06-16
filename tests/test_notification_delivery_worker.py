from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.notifications.events import NotificationCandidate, NotificationEventType
from app.notifications.matching import NotificationDeliveryTarget
from app.notifications.models import NotificationDelivery
from app.notifications.repository import (
    PENDING_DELIVERY_STATUS,
    SKIPPED_DELIVERY_STATUS,
    create_pending_deliveries,
    get_or_create_notification_event,
)
from app.notifications.schemas import PushPlatform
from app.notifications.sender import NoopPushSender
from app.workers.notification_delivery_worker import process_pending_deliveries_once

test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    poolclass=StaticPool,
)
db_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def clean_database():
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield


def candidate() -> NotificationCandidate:
    return NotificationCandidate(
        line_id="victoria",
        event_type=NotificationEventType.DISRUPTION_STARTED,
        observed_at=datetime(2026, 6, 16, 8, 0, tzinfo=UTC),
        severity=6,
        status_description="Severe Delays",
        reason="Signal failure",
        dedupe_key="event-key",
    )


def target(device_id: str) -> NotificationDeliveryTarget:
    return NotificationDeliveryTarget(
        device_id=device_id,
        platform=PushPlatform.IOS,
        push_token=f"{device_id}-token",
    )


async def create_pending_delivery_batch(device_ids: list[str]) -> None:
    async with db_session_factory() as session:
        event, _ = await get_or_create_notification_event(session, candidate())
        await create_pending_deliveries(
            session,
            event,
            [target(device_id) for device_id in device_ids],
        )


async def stored_deliveries() -> list[NotificationDelivery]:
    async with db_session_factory() as session:
        return list(
            await session.scalars(select(NotificationDelivery).order_by(NotificationDelivery.id))
        )


async def test_process_pending_deliveries_once_uses_noop_sender() -> None:
    await create_pending_delivery_batch(["install-1"])

    processed_count = await process_pending_deliveries_once(
        sender=NoopPushSender(),
        session_factory=db_session_factory,
    )

    [delivery] = await stored_deliveries()
    assert processed_count == 1
    assert delivery.status == SKIPPED_DELIVERY_STATUS
    assert delivery.failure_reason == "Push sender is not configured"


async def test_process_pending_deliveries_once_respects_limit() -> None:
    await create_pending_delivery_batch(["install-1", "install-2"])

    processed_count = await process_pending_deliveries_once(
        sender=NoopPushSender(),
        limit=1,
        session_factory=db_session_factory,
    )

    deliveries = await stored_deliveries()
    assert processed_count == 1
    assert [delivery.status for delivery in deliveries] == [
        SKIPPED_DELIVERY_STATUS,
        PENDING_DELIVERY_STATUS,
    ]
