from fastapi import APIRouter

from app.api.routes import health, line_status, notifications, operations

router = APIRouter()
router.include_router(health.router)
router.include_router(line_status.router)
router.include_router(notifications.router)
router.include_router(operations.router)
