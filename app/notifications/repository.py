from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.notifications.events import NotificationCandidate
from app.notifications.matching import NotificationDeliveryTarget
from app.notifications.models import (
    NotificationDelivery,
    NotificationDevice,
    NotificationEvent,
    NotificationLinePreference,
    NotificationPreferences,
)
from app.notifications.schemas import (
    NotificationDeviceRegistration,
    NotificationPreferencesUpdate,
)

PENDING_DELIVERY_STATUS = "pending"
SENT_DELIVERY_STATUS = "sent"
FAILED_DELIVERY_STATUS = "failed"
SKIPPED_DELIVERY_STATUS = "skipped"


def utc_now() -> datetime:
    return datetime.now(UTC)


def _load_preferences():
    return selectinload(NotificationDevice.preferences).selectinload(NotificationPreferences.lines)


async def get_device(
    session: AsyncSession,
    device_id: str,
) -> NotificationDevice | None:
    statement = (
        select(NotificationDevice)
        .where(NotificationDevice.device_id == device_id)
        .options(_load_preferences())
    )
    return await session.scalar(statement)


async def get_notification_devices_with_preferences(
    session: AsyncSession,
) -> list[NotificationDevice]:
    statement = (
        select(NotificationDevice)
        .where(NotificationDevice.preferences.has())
        .options(_load_preferences())
    )
    return list((await session.scalars(statement)).all())


async def upsert_device(
    session: AsyncSession,
    device_id: str,
    registration: NotificationDeviceRegistration,
) -> NotificationDevice:
    now = utc_now()
    device = await get_device(session, device_id)
    device_with_token = await session.scalar(
        select(NotificationDevice).where(
            NotificationDevice.push_token == registration.push_token,
            NotificationDevice.device_id != device_id,
        )
    )
    if device_with_token is not None:
        await session.delete(device_with_token)
        await session.flush()

    if device is None:
        device = NotificationDevice(
            device_id=device_id,
            platform=registration.platform.value,
            push_token=registration.push_token,
            enabled=True,
            app_version=registration.app_version,
            created_at=now,
            updated_at=now,
            last_seen_at=now,
        )
        session.add(device)
    else:
        device.platform = registration.platform.value
        device.push_token = registration.push_token
        device.enabled = True
        device.app_version = registration.app_version
        device.updated_at = now
        device.last_seen_at = now

    await session.commit()
    await session.refresh(device)
    return device


async def get_preferences(
    session: AsyncSession,
    device_id: str,
) -> NotificationPreferences | None:
    statement = (
        select(NotificationPreferences)
        .where(NotificationPreferences.device_id == device_id)
        .options(selectinload(NotificationPreferences.lines))
    )
    return await session.scalar(statement)


async def upsert_preferences(
    session: AsyncSession,
    device_id: str,
    update: NotificationPreferencesUpdate,
) -> NotificationPreferences | None:
    device = await get_device(session, device_id)
    if device is None:
        return None

    now = utc_now()
    preferences = await get_preferences(session, device_id)
    if preferences is None:
        preferences = NotificationPreferences(
            device_id=device_id,
            timezone=update.timezone,
            created_at=now,
            updated_at=now,
        )
        session.add(preferences)
    else:
        preferences.timezone = update.timezone
        preferences.updated_at = now

    existing_lines = {line.line_id: line for line in preferences.lines}
    updated_lines: list[NotificationLinePreference] = []
    for line_update in update.lines:
        line = existing_lines.get(line_update.line_id)
        if line is None:
            line = NotificationLinePreference(
                device_id=device_id,
                line_id=line_update.line_id,
            )
        line.enabled = line_update.enabled
        line.severity_threshold = line_update.severity_threshold.value
        line.notify_recoveries = line_update.notify_recoveries
        line.schedule_preset = line_update.schedule_preset.value
        line.custom_schedules = [
            schedule.model_dump(mode="json") for schedule in line_update.custom_schedules
        ]
        updated_lines.append(line)
    preferences.lines = updated_lines

    await session.commit()
    await session.refresh(preferences)
    return preferences


async def disable_device(session: AsyncSession, device_id: str) -> NotificationDevice | None:
    device = await get_device(session, device_id)
    if device is None:
        return None

    now = utc_now()
    device.enabled = False
    device.updated_at = now

    await session.commit()
    await session.refresh(device)
    return device


async def enable_device(session: AsyncSession, device_id: str) -> NotificationDevice | None:
    device = await get_device(session, device_id)
    if device is None:
        return None

    now = utc_now()
    device.enabled = True
    device.updated_at = now

    await session.commit()
    await session.refresh(device)
    return device


async def delete_device(session: AsyncSession, device_id: str) -> bool:
    device = await get_device(session, device_id)
    if device is None:
        return False

    await session.delete(device)
    await session.commit()
    return True


async def get_or_create_notification_event(
    session: AsyncSession,
    candidate: NotificationCandidate,
) -> tuple[NotificationEvent, bool]:
    existing_event = await session.scalar(
        select(NotificationEvent).where(
            NotificationEvent.dedupe_key == candidate.dedupe_key,
        )
    )
    if existing_event is not None:
        return existing_event, False

    event = NotificationEvent(
        dedupe_key=candidate.dedupe_key,
        line_id=candidate.line_id,
        event_type=candidate.event_type.value,
        observed_at=candidate.observed_at,
        severity=candidate.severity,
        status_description=candidate.status_description,
        reason=candidate.reason,
        created_at=utc_now(),
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event, True


async def create_pending_deliveries(
    session: AsyncSession,
    event: NotificationEvent,
    targets: list[NotificationDeliveryTarget],
) -> list[NotificationDelivery]:
    if not targets:
        return []

    targets_by_device_id = {target.device_id: target for target in targets}
    existing_device_ids = set(
        (
            await session.scalars(
                select(NotificationDelivery.device_id).where(
                    NotificationDelivery.event_id == event.id,
                    NotificationDelivery.device_id.in_(
                        list(targets_by_device_id),
                    ),
                )
            )
        ).all()
    )
    now = utc_now()
    deliveries = [
        NotificationDelivery(
            event_id=event.id,
            device_id=target.device_id,
            platform=target.platform.value,
            push_token=target.push_token,
            status=PENDING_DELIVERY_STATUS,
            provider_message_id=None,
            failure_reason=None,
            created_at=now,
            updated_at=now,
        )
        for target in targets_by_device_id.values()
        if target.device_id not in existing_device_ids
    ]
    session.add_all(deliveries)
    await session.commit()
    for delivery in deliveries:
        await session.refresh(delivery)
    return deliveries


async def get_pending_deliveries(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[NotificationDelivery]:
    statement = (
        select(NotificationDelivery)
        .where(NotificationDelivery.status == PENDING_DELIVERY_STATUS)
        .options(selectinload(NotificationDelivery.event))
        .order_by(NotificationDelivery.created_at, NotificationDelivery.id)
        .limit(limit)
    )
    return list((await session.scalars(statement)).all())


async def mark_delivery_sent(
    session: AsyncSession,
    delivery: NotificationDelivery,
    *,
    provider_message_id: str | None,
) -> NotificationDelivery:
    delivery.status = SENT_DELIVERY_STATUS
    delivery.provider_message_id = provider_message_id
    delivery.failure_reason = None
    delivery.updated_at = utc_now()
    await session.commit()
    await session.refresh(delivery)
    return delivery


async def mark_delivery_failed(
    session: AsyncSession,
    delivery: NotificationDelivery,
    *,
    failure_reason: str,
) -> NotificationDelivery:
    delivery.status = FAILED_DELIVERY_STATUS
    delivery.failure_reason = failure_reason
    delivery.updated_at = utc_now()
    await session.commit()
    await session.refresh(delivery)
    return delivery


async def mark_delivery_skipped(
    session: AsyncSession,
    delivery: NotificationDelivery,
    *,
    failure_reason: str | None = None,
) -> NotificationDelivery:
    delivery.status = SKIPPED_DELIVERY_STATUS
    delivery.failure_reason = failure_reason
    delivery.updated_at = utc_now()
    await session.commit()
    await session.refresh(delivery)
    return delivery
