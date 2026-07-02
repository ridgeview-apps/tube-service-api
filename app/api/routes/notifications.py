from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_api_key
from app.config import Settings, get_settings
from app.database import get_session
from app.notifications.models import (
    NotificationDelivery,
    NotificationDevice,
    NotificationEvent,
    NotificationPreferences,
)
from app.notifications.repository import (
    delete_device,
    disable_device,
    enable_device,
    get_device,
    get_preferences,
    upsert_device,
    upsert_preferences,
)
from app.notifications.schemas import (
    NotificationDeviceRead,
    NotificationDeviceRegistration,
    NotificationPreferencesRead,
    NotificationPreferencesUpdate,
    NotificationTestPushRead,
    PushPlatform,
)
from app.notifications.sender import (
    NoopPushSender,
    PushSender,
    PushSendStatus,
    build_configured_push_sender,
)

router = APIRouter(
    prefix="/v1/notification-devices",
    tags=["notifications"],
    dependencies=[Depends(require_api_key)],
)


def get_push_sender(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PushSender:
    return build_configured_push_sender(settings)


@router.put("/{device_id}", response_model=NotificationDeviceRead)
async def register_notification_device(
    device_id: str,
    registration: NotificationDeviceRegistration,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationDevice:
    return await upsert_device(session, device_id, registration)


@router.get("/{device_id}/preferences", response_model=NotificationPreferencesRead)
async def read_notification_preferences(
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationPreferences:
    preferences = await get_preferences(session, device_id)
    if preferences is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification preferences not found",
        )
    return preferences


@router.put("/{device_id}/preferences", response_model=NotificationPreferencesRead)
async def update_notification_preferences(
    device_id: str,
    update: NotificationPreferencesUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationPreferences:
    preferences = await upsert_preferences(session, device_id, update)
    if preferences is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification device not found",
        )
    return preferences


@router.post("/{device_id}/disable", response_model=NotificationDeviceRead)
async def disable_notification_device(
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationDevice:
    device = await disable_device(session, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification device not found",
        )
    return device


@router.post("/{device_id}/enable", response_model=NotificationDeviceRead)
async def enable_notification_device(
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationDevice:
    device = await enable_device(session, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification device not found",
        )
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification_device(
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    deleted = await delete_device(session, device_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification device not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{device_id}/test-push", response_model=NotificationTestPushRead)
async def send_test_push_notification(
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    sender: Annotated[PushSender, Depends(get_push_sender)],
) -> NotificationTestPushRead:
    if not settings.apns_test_push_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test push endpoint is not enabled",
        )
    if isinstance(sender, NoopPushSender):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APNs is not configured",
        )

    device = await get_device(session, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification device not found",
        )
    if device.platform != PushPlatform.IOS.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test push is only supported for iOS devices",
        )

    observed_at = datetime.now(UTC)
    result = await sender.send(
        delivery=NotificationDelivery(
            id=0,
            event_id=0,
            device_id=device.device_id,
            platform=device.platform,
            push_token=device.push_token,
            app_variant=device.app_variant,
            status="test",
            created_at=observed_at,
            updated_at=observed_at,
        ),
        event=NotificationEvent(
            id=0,
            dedupe_key=f"test:{device.device_id}:{int(observed_at.timestamp())}",
            line_id="test",
            event_type="test",
            observed_at=observed_at,
            severity=0,
            status_description="Test notification",
            reason=None,
            created_at=observed_at,
        ),
    )

    if result.status == PushSendStatus.SKIPPED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.failure_reason or "Test push was skipped",
        )

    return NotificationTestPushRead(
        device_id=device.device_id,
        status=result.status.value,
        provider_message_id=result.provider_message_id,
        failure_reason=result.failure_reason,
    )
