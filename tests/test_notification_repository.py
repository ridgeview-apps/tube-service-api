from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.notifications.events import NotificationCandidate, NotificationEventType
from app.notifications.matching import NotificationDeliveryTarget
from app.notifications.repository import (
    FAILED_DELIVERY_STATUS,
    PENDING_DELIVERY_STATUS,
    SENT_DELIVERY_STATUS,
    SKIPPED_DELIVERY_STATUS,
    create_pending_deliveries,
    get_or_create_notification_event,
    mark_delivery_failed,
    mark_delivery_sent,
    mark_delivery_skipped,
)
from app.notifications.schemas import PushPlatform

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


def candidate(
    *,
    dedupe_key: str = "same-event-key",
) -> NotificationCandidate:
    return NotificationCandidate(
        line_id="victoria",
        event_type=NotificationEventType.DISRUPTION_STARTED,
        observed_at=datetime(2026, 6, 16, 8, 0, tzinfo=UTC),
        severity=9,
        status_description="Minor Delays",
        reason="Signal failure",
        dedupe_key=dedupe_key,
    )


def target(
    *,
    device_id: str = "install-123",
) -> NotificationDeliveryTarget:
    return NotificationDeliveryTarget(
        device_id=device_id,
        platform=PushPlatform.IOS,
        push_token=f"{device_id}-token",
        app_variant="production",
    )


async def test_get_or_create_notification_event_is_idempotent() -> None:
    async with db_session_factory() as session:
        first_event, first_created = await get_or_create_notification_event(
            session,
            candidate(),
        )
        second_event, second_created = await get_or_create_notification_event(
            session,
            candidate(),
        )

    assert first_created is True
    assert second_created is False
    assert first_event.id == second_event.id
    assert second_event.dedupe_key == "same-event-key"
    assert second_event.line_id == "victoria"
    assert second_event.event_type == "disruption_started"
    assert second_event.severity == 9
    assert second_event.status_description == "Minor Delays"
    assert second_event.reason == "Signal failure"


async def test_create_pending_deliveries_skips_existing_event_device_pairs() -> None:
    async with db_session_factory() as session:
        event, _ = await get_or_create_notification_event(session, candidate())

        first_deliveries = await create_pending_deliveries(
            session,
            event,
            [target(device_id="install-1"), target(device_id="install-2")],
        )
        second_deliveries = await create_pending_deliveries(
            session,
            event,
            [target(device_id="install-1"), target(device_id="install-3")],
        )

    assert [delivery.device_id for delivery in first_deliveries] == [
        "install-1",
        "install-2",
    ]
    assert [delivery.device_id for delivery in second_deliveries] == ["install-3"]
    assert all(delivery.status == PENDING_DELIVERY_STATUS for delivery in first_deliveries)
    assert second_deliveries[0].platform == "ios"
    assert second_deliveries[0].push_token == "install-3-token"


async def test_create_pending_deliveries_deduplicates_targets_in_same_batch() -> None:
    async with db_session_factory() as session:
        event, _ = await get_or_create_notification_event(session, candidate())

        deliveries = await create_pending_deliveries(
            session,
            event,
            [target(device_id="install-1"), target(device_id="install-1")],
        )

    assert [delivery.device_id for delivery in deliveries] == ["install-1"]


async def test_create_pending_deliveries_returns_empty_list_without_targets() -> None:
    async with db_session_factory() as session:
        event, _ = await get_or_create_notification_event(session, candidate())

        deliveries = await create_pending_deliveries(session, event, [])

    assert deliveries == []


async def test_delivery_status_updates_are_persisted() -> None:
    async with db_session_factory() as session:
        event, _ = await get_or_create_notification_event(session, candidate())
        [delivery] = await create_pending_deliveries(session, event, [target()])

        sent_delivery = await mark_delivery_sent(
            session,
            delivery,
            provider_message_id="provider-123",
        )
        sent_status = sent_delivery.status
        sent_provider_message_id = sent_delivery.provider_message_id
        failed_delivery = await mark_delivery_failed(
            session,
            sent_delivery,
            failure_reason="Expired token",
        )
        failed_status = failed_delivery.status
        failed_reason = failed_delivery.failure_reason
        skipped_delivery = await mark_delivery_skipped(
            session,
            failed_delivery,
            failure_reason="Duplicate delivery",
        )
        skipped_status = skipped_delivery.status
        skipped_reason = skipped_delivery.failure_reason

    assert sent_status == SENT_DELIVERY_STATUS
    assert sent_provider_message_id == "provider-123"
    assert failed_status == FAILED_DELIVERY_STATUS
    assert failed_reason == "Expired token"
    assert skipped_status == SKIPPED_DELIVERY_STATUS
    assert skipped_reason == "Duplicate delivery"
