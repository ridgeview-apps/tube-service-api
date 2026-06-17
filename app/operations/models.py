from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WorkerRun(Base):
    __tablename__ = "worker_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    worker_name: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), index=True)
    processed_count: Mapped[int] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
