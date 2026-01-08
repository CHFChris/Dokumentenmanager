from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class LoginDevice(Base):
    __tablename__ = "login_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Hash ueber Fingerprint (z. B. User-Agent + IP)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    last_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint_hash", name="ux_login_devices_user_fingerprint"),
    )
