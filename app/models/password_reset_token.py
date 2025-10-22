# app/models/password_reset_token.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        # für schnelles Rate-Limit-Checking
        {"mysql_engine": "InnoDB"},
    )

    # Primärschlüssel
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Nutzerbezug
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # SHA-256 Hex (64 Zeichen) des Tokens
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # Ablauf / Nutzung
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Erzeugungszeitpunkt (Server-Default)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
