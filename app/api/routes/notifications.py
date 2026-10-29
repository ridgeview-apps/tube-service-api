from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_api_key
from app.config import Settings, get_settings
from app.database import get_session
from app.notifications.models import NotificationDevice, NotificationPreferences
from app.notifications.repository import (
    create_test_delivery,
    delete_device,
    disable_device,
    enable_device,
    get_device,
    get_preferences,
    get_test_delivery,
    patch_preferences,
    upsert_device,
    upsert_preferences,
)
from app.notifications.schemas import (
    NotificationDeviceRead,
    NotificationDeviceRegistration,
    NotificationPreferencesPatch,
    NotificationPreferencesRead,
    NotificationPreferencesUpdate,
    NotificationTestPushRead,
    PushPlatform,
)

router = APIRouter(
    prefix="/v1/notification-devices",
    tags=["notifications"],
    dependencies=[Depends(require_api_key)],
)

PATCH_PREFERENCES_EXAMPLES = {
    "update-and-remove": {
        "summary": "Update one line and remove another",
        "value": {
            "lines": {
                "victoria": {"enabled": False},
                "central": None,
            }
        },
    },
    "add-line": {
        "summary": "Add a fully specified line",
        "value": {
            "lines": {
                "victoria": {
                    "enabled": True,
                    "severity_threshold": "minor_delays",
                    "notify_recoveries": True,
                    "schedules": [
                        {
                            "days": ["mon", "tue", "wed", "thu", "fri"],
                            "windows": [
                                {
                                    "start_time": "06:30",
                                    "end_time": "09:30",
                                }
                            ],
                        }
                    ],
                }
            }
        },
    },
}


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


@router.patch(
    "/{device_id}/preferences",
    response_model=NotificationPreferencesRead,
    openapi_extra={
        "requestBody": {
            "content": {"application/merge-patch+json": {"examples": PATCH_PREFERENCES_EXAMPLES}}
        }
    },
)
async def patch_notification_preferences(
    device_id: str,
    patch: Annotated[
        NotificationPreferencesPatch,
        Body(
            media_type="application/merge-patch+json",
            description=(
                "Only listed lines and fields change. Use null to remove a line; "
                "a new line must include every preference field."
            ),
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationPreferences:
    try:
        preferences = await patch_preferences(session, device_id, patch)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
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


@router.post(
    "/{device_id}/test-push",
    response_model=NotificationTestPushRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_test_push_notification(
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationTestPushRead:
    if not settings.apns_test_push_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test push endpoint is not enabled",
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

    delivery = await create_test_delivery(session, device)

    return NotificationTestPushRead(
        delivery_id=delivery.id,
        device_id=device.device_id,
        status=delivery.status,
        provider_message_id=delivery.provider_message_id,
        failure_reason=delivery.failure_reason,
    )


@router.get(
    "/{device_id}/test-push/{delivery_id}",
    response_model=NotificationTestPushRead,
)
async def read_test_push_notification(
    device_id: str,
    delivery_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationTestPushRead:
    if not settings.apns_test_push_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test push endpoint is not enabled",
        )

    delivery = await get_test_delivery(
        session,
        device_id=device_id,
        delivery_id=delivery_id,
    )
    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test push delivery not found",
        )

    return NotificationTestPushRead(
        delivery_id=delivery.id,
        device_id=delivery.device_id,
        status=delivery.status,
        provider_message_id=delivery.provider_message_id,
        failure_reason=delivery.failure_reason,
    )
