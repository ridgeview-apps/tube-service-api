from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    device: Mapped[NotificationDevice] = relationship(back_populates="preferences")
    lines: Mapped[list["NotificationLinePreference"]] = relationship(
        back_populates="preferences",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="NotificationLinePreference.line_id",
    )


class NotificationLinePreference(Base):
    __tablename__ = "notification_line_preferences"

    device_id: Mapped[str] = mapped_column(
        ForeignKey("notification_preferences.device_id", ondelete="CASCADE"),
        primary_key=True,
    )
    line_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    severity_threshold: Mapped[str] = mapped_column(String(32))
    notify_recoveries: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_preset: Mapped[str] = mapped_column(String(32))
    custom_schedules: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    preferences: Mapped[NotificationPreferences] = relationship(back_populates="lines")


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    line_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    severity: Mapped[int] = mapped_column(Integer)
    status_description: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deliveries: Mapped[list["NotificationDelivery"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "device_id",
            name="uq_notification_delivery_event_device",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("notification_events.id", ondelete="CASCADE"),
        index=True,
    )
    device_id: Mapped[str] = mapped_column(String(128), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    push_token: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16))
    provider_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event: Mapped[NotificationEvent] = relationship(back_populates="deliveries")
