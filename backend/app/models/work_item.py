from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RECEIVED','ANALYSING','READY_FOR_REVIEW','COMPLETED','FAILED')",
            name="valid_status",
        ),
        CheckConstraint("attempts >= 0", name="nonnegative_attempts"),
        CheckConstraint(
            "(status IN ('READY_FOR_REVIEW','COMPLETED')) = (analysis IS NOT NULL)",
            name="analysis_state",
        ),
        CheckConstraint(
            "(status = 'FAILED' AND error_code IS NOT NULL AND error_message IS NOT NULL) OR (status <> 'FAILED' AND error_code IS NULL AND error_message IS NULL)",
            name="error_state",
        ),
        CheckConstraint(
            "(status = 'ANALYSING' AND attempt_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR (status <> 'ANALYSING' AND attempt_token IS NULL AND lease_expires_at IS NULL)",
            name="lease_state",
        ),
        Index("ix_work_items_status_created", "status", "created_at"),
        Index("ix_work_items_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    external_id: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED", server_default="RECEIVED")
    analysis: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    ai_provider: Mapped[str | None] = mapped_column(String(50))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
