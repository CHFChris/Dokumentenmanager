# app/repositories/verification_events_repo.py
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Enum as SAEnum, DateTime, ForeignKey, BIGINT
from sqlalchemy.orm import declarative_base
from datetime import datetime
from app.db.database import Base

class EmailVerificationEvent(Base):
    __tablename__ = "email_verification_events"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    kind: Mapped[str] = mapped_column(SAEnum("send","resend", name="verification_event_kind"))
