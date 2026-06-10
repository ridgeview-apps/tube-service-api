from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LineStatusSnapshot(Base):
    __tablename__ = "line_status_snapshots"
    __table_args__ = (Index("ix_snapshot_line_observed", "line_id", "observed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[str] = mapped_column(String(64))
    line_name: Mapped[str] = mapped_column(String(128))
    mode_name: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    statuses: Mapped[list["LineStatus"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="LineStatus.id",
    )


class LineStatus(Base):
    __tablename__ = "line_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("line_status_snapshots.id", ondelete="CASCADE"),
        index=True,
    )
    status_severity: Mapped[int] = mapped_column(Integer)
    status_description: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    disruption_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    additional_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot: Mapped[LineStatusSnapshot] = relationship(back_populates="statuses")
