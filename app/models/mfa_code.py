# app/models/mfa_code.py
from __future__ import annotations

import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, BigInteger
from sqlalchemy.orm import relationship

from app.db.database import Base


class MFACode(Base):
    __tablename__ = "mfa_codes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    code = Column(String(16), nullable=False)
    purpose = Column(String(32), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="mfa_codes")
