from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LineStatusSnapshot(Base):
    __tablename__ = "line_status_snapshots"
    __table_args__ = (Index("ix_snapshot_line_observed", "line_id", "observed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[str] = mapped_column(String(64))
    line_name: Mapped[str] = mapped_column(String(128))
    mode_name: Mapped[str] = mapped_column(String(64))
    status_severity: Mapped[int] = mapped_column(Integer)
    status_description: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
