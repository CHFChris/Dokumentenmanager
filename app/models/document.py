# app/models/document.py
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

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.document_version import DocumentVersion
    from app.models.category import Category  # neu


class Document(Base):
    __tablename__ = "documents"

    # ------------------------------------------------------------
    # Core
    # ------------------------------------------------------------
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------
    # Struktur (optional)
    # ------------------------------------------------------------
    folder_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Kategorie (für Filter etc.)
    category_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ------------------------------------------------------------
    # Datei-Infos
    # ------------------------------------------------------------
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # ------------------------------------------------------------
    # OCR / KI
    # ------------------------------------------------------------
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------
    # Speicher-Provider (lokal/S3/etc.)
    # ------------------------------------------------------------
    storage_provider_id: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
    )

    # ------------------------------------------------------------
    # Flags & Zeit
    # ------------------------------------------------------------
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ------------------------------------------------------------
    # Beziehungen
    # ------------------------------------------------------------
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

    category: Mapped[Optional["Category"]] = relationship(
        "Category",
        back_populates="documents",
    )

    # ------------------------------------------------------------
    # Kompatibilitäts-Aliasse
    # ------------------------------------------------------------
    @property
    def name(self) -> str:
        """Alias für filename (z. B. im Frontend/alten Services)."""
        return self.filename

    @name.setter
    def name(self, value: str) -> None:
        self.filename = value

    @property
    def size(self) -> int:
        """Alias für size_bytes."""
        return self.size_bytes

    @size.setter
    def size(self, value: int) -> None:
        self.size_bytes = value

    @property
    def sha256(self) -> Optional[str]:
        """Alias für checksum_sha256."""
        return self.checksum_sha256

    @sha256.setter
    def sha256(self, value: Optional[str]) -> None:
        self.checksum_sha256 = value

    # ------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} "
            f"filename={self.filename!r} "
            f"size={self.size_bytes}B>"
        )
