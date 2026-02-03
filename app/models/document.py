from __future__ import annotations

from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    BigInteger,
    SmallInteger,
    Boolean,
    ForeignKey,
    DateTime,
    func,
    Text,
)

from app.db.database import Base
from app.models.document_categories import document_categories

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.document_version import DocumentVersion
    from app.models.category import Category


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    folder_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    stored_name: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
    )

    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    storage_provider_id: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_favorite: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship(
        "User",
        back_populates="documents",
        passive_deletes=True,
    )

    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    categories: Mapped[List["Category"]] = relationship(
        "Category",
        secondary=document_categories,
        back_populates="documents",
        lazy="selectin",
    )

    @property
    def name(self) -> str:
        return self.filename

    @name.setter
    def name(self, value: str) -> None:
        self.filename = value

    @property
    def size(self) -> int:
        return self.size_bytes

    @size.setter
    def size(self, value: int) -> None:
        self.size_bytes = value

    @property
    def sha256(self) -> Optional[str]:
        return self.checksum_sha256

    @sha256.setter
    def sha256(self, value: Optional[str]) -> None:
        self.checksum_sha256 = value

    @property
    def sha256_hash(self) -> Optional[str]:
        return self.checksum_sha256

    @sha256_hash.setter
    def sha256_hash(self, value: Optional[str]) -> None:
        self.checksum_sha256 = value

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} size={self.size_bytes}B>"
