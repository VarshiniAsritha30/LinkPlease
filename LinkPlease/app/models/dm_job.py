import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DMJobStatus(str, enum.Enum):
    QUEUED = "queued"
    SENDING = "sending"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"


class DMJob(Base):
    __tablename__ = "dm_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    comment_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default=DMJobStatus.QUEUED.value, nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    dm_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("rule_id", "user_id", name="uq_rule_user"),
    )
