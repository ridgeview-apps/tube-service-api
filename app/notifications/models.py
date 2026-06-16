from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NotificationDevice(Base):
    __tablename__ = "notification_devices"

    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    platform: Mapped[str] = mapped_column(String(16))
    push_token: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failure_count: Mapped[int] = mapped_column(default=0)
    preferences: Mapped["NotificationPreferences | None"] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )


class NotificationPreferences(Base):
    __tablename__ = "notification_preferences"

    device_id: Mapped[str] = mapped_column(
        ForeignKey("notification_devices.device_id", ondelete="CASCADE"),
        primary_key=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    line_ids: Mapped[list[str]] = mapped_column(JSON)
    severity_threshold: Mapped[str] = mapped_column(String(32))
    notify_recoveries: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String(64))
    schedule_preset: Mapped[str] = mapped_column(String(32))
    custom_schedules: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    device: Mapped[NotificationDevice] = relationship(back_populates="preferences")
