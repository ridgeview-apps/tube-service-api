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
    FAILED_DELIVERY_STATUS,
    PENDING_DELIVERY_STATUS,
    SENT_DELIVERY_STATUS,
    SKIPPED_DELIVERY_STATUS,
    create_pending_deliveries,
    get_or_create_notification_event,
    mark_delivery_sent,
)
from app.notifications.schemas import PushPlatform
from app.notifications.sender import (
    PushSendResult,
    PushSendStatus,
    process_pending_deliveries,
)

test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    poolclass=StaticPool,
)
db_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


class FakePushSender:
    def __init__(self, results: list[PushSendResult]) -> None:
        self.results = results
        self.sent_delivery_ids: list[int] = []
        self.sent_event_ids: list[int] = []

    async def send(self, *, delivery, event):
        self.sent_delivery_ids.append(delivery.id)
        self.sent_event_ids.append(event.id)
        return self.results.pop(0)


@pytest.fixture(autouse=True)
async def clean_database():
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield


def candidate(
    *,
    dedupe_key: str = "event-key",
) -> NotificationCandidate:
    return NotificationCandidate(
        line_id="victoria",
        event_type=NotificationEventType.DISRUPTION_STARTED,
        observed_at=datetime(2026, 6, 16, 8, 0, tzinfo=UTC),
        severity=6,
        status_description="Severe Delays",
        reason="Signal failure",
        dedupe_key=dedupe_key,
    )


def target(device_id: str) -> NotificationDeliveryTarget:
    return NotificationDeliveryTarget(
        device_id=device_id,
        platform=PushPlatform.IOS,
        push_token=f"{device_id}-token",
        app_variant="production",
    )


async def create_delivery_batch(device_ids: list[str]) -> list[NotificationDelivery]:
    async with db_session_factory() as session:
        event, _ = await get_or_create_notification_event(session, candidate())
        return await create_pending_deliveries(
            session,
            event,
            [target(device_id) for device_id in device_ids],
        )


async def stored_deliveries() -> list[NotificationDelivery]:
    async with db_session_factory() as session:
        return list(
            await session.scalars(select(NotificationDelivery).order_by(NotificationDelivery.id))
        )


async def test_process_pending_deliveries_marks_successful_sends() -> None:
    [delivery] = await create_delivery_batch(["install-1"])
    sender = FakePushSender(
        [
            PushSendResult(
                status=PushSendStatus.SENT,
                provider_message_id="apns-message-id",
            )
        ]
    )

    async with db_session_factory() as session:
        processed_count = await process_pending_deliveries(session=session, sender=sender)

    [stored_delivery] = await stored_deliveries()
    assert processed_count == 1
    assert sender.sent_delivery_ids == [delivery.id]
    assert stored_delivery.status == SENT_DELIVERY_STATUS
    assert stored_delivery.provider_message_id == "apns-message-id"
    assert stored_delivery.failure_reason is None


async def test_process_pending_deliveries_marks_failed_sends() -> None:
    await create_delivery_batch(["install-1"])
    sender = FakePushSender(
        [
            PushSendResult(
                status=PushSendStatus.FAILED,
                failure_reason="Expired token",
            )
        ]
    )

    async with db_session_factory() as session:
        processed_count = await process_pending_deliveries(session=session, sender=sender)

    [stored_delivery] = await stored_deliveries()
    assert processed_count == 1
    assert stored_delivery.status == FAILED_DELIVERY_STATUS
    assert stored_delivery.failure_reason == "Expired token"


async def test_process_pending_deliveries_marks_skipped_sends() -> None:
    await create_delivery_batch(["install-1"])
    sender = FakePushSender(
        [
            PushSendResult(
                status=PushSendStatus.SKIPPED,
                failure_reason="Unsupported platform",
            )
        ]
    )

    async with db_session_factory() as session:
        processed_count = await process_pending_deliveries(session=session, sender=sender)

    [stored_delivery] = await stored_deliveries()
    assert processed_count == 1
    assert stored_delivery.status == SKIPPED_DELIVERY_STATUS
    assert stored_delivery.failure_reason == "Unsupported platform"


async def test_process_pending_deliveries_respects_limit() -> None:
    await create_delivery_batch(["install-1", "install-2"])
    sender = FakePushSender(
        [
            PushSendResult(status=PushSendStatus.SENT, provider_message_id="first"),
            PushSendResult(status=PushSendStatus.SENT, provider_message_id="second"),
        ]
    )

    async with db_session_factory() as session:
        processed_count = await process_pending_deliveries(
            session=session,
            sender=sender,
            limit=1,
        )

    deliveries = await stored_deliveries()
    assert processed_count == 1
    assert [delivery.status for delivery in deliveries] == [
        SENT_DELIVERY_STATUS,
        PENDING_DELIVERY_STATUS,
    ]


async def test_process_pending_deliveries_ignores_non_pending_deliveries() -> None:
    [delivery] = await create_delivery_batch(["install-1"])
    async with db_session_factory() as session:
        persisted_delivery = await session.get(NotificationDelivery, delivery.id)
        assert persisted_delivery is not None
        await mark_delivery_sent(
            session,
            persisted_delivery,
            provider_message_id="already-sent",
        )

    sender = FakePushSender([PushSendResult(status=PushSendStatus.SENT)])
    async with db_session_factory() as session:
        processed_count = await process_pending_deliveries(session=session, sender=sender)

    [stored_delivery] = await stored_deliveries()
    assert processed_count == 0
    assert sender.sent_delivery_ids == []
    assert stored_delivery.provider_message_id == "already-sent"
