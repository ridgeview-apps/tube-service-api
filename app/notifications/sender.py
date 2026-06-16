from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import NotificationDelivery, NotificationEvent
from app.notifications.repository import (
    get_pending_deliveries,
    mark_delivery_failed,
    mark_delivery_sent,
    mark_delivery_skipped,
)


class PushSendStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class PushSendResult:
    status: PushSendStatus
    provider_message_id: str | None = None
    failure_reason: str | None = None


class PushSender(Protocol):
    async def send(
        self,
        *,
        delivery: NotificationDelivery,
        event: NotificationEvent,
    ) -> PushSendResult:
        pass


class NoopPushSender:
    async def send(
        self,
        *,
        delivery: NotificationDelivery,
        event: NotificationEvent,
    ) -> PushSendResult:
        return PushSendResult(
            status=PushSendStatus.SKIPPED,
            failure_reason="Push sender is not configured",
        )


async def process_pending_deliveries(
    *,
    session: AsyncSession,
    sender: PushSender,
    limit: int = 100,
) -> int:
    deliveries = await get_pending_deliveries(session, limit=limit)
    processed_count = 0

    for delivery in deliveries:
        result = await sender.send(delivery=delivery, event=delivery.event)
        match result.status:
            case PushSendStatus.SENT:
                await mark_delivery_sent(
                    session,
                    delivery,
                    provider_message_id=result.provider_message_id,
                )
            case PushSendStatus.FAILED:
                await mark_delivery_failed(
                    session,
                    delivery,
                    failure_reason=result.failure_reason or "Push provider failed",
                )
            case PushSendStatus.SKIPPED:
                await mark_delivery_skipped(
                    session,
                    delivery,
                    failure_reason=result.failure_reason,
                )
        processed_count += 1

    return processed_count
