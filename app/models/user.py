# app/models/user.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING, List

from sqlalchemy import Integer, SmallInteger, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.email_verification_token import EmailVerificationToken
    from app.models.password_reset_token import PasswordResetToken


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    email_verification_tokens: Mapped[List["EmailVerificationToken"]] = relationship(
        "EmailVerificationToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    password_reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<User id={self.id} "
            f"username={self.username!r} "
            f"email={self.email!r} "
            f"role_id={self.role_id} "
            f"verified={self.is_verified}>"
        )
