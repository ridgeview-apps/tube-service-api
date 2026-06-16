from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_api_key
from app.database import get_session
from app.notifications.repository import (
    delete_device,
    disable_device,
    get_preferences,
    upsert_device,
    upsert_preferences,
)
from app.notifications.schemas import (
    NotificationDeviceRead,
    NotificationDeviceRegistration,
    NotificationPreferencesRead,
    NotificationPreferencesUpdate,
)

router = APIRouter(
    prefix="/v1/notification-devices",
    tags=["notifications"],
    dependencies=[Depends(require_api_key)],
)


@router.put("/{device_id}", response_model=NotificationDeviceRead)
async def register_notification_device(
    device_id: str,
    registration: NotificationDeviceRegistration,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationDeviceRead:
    return await upsert_device(session, device_id, registration)


@router.get("/{device_id}/preferences", response_model=NotificationPreferencesRead)
async def read_notification_preferences(
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationPreferencesRead:
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
) -> NotificationPreferencesRead:
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
) -> NotificationDeviceRead:
    device = await disable_device(session, device_id)
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
