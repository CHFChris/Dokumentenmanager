from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PendingUpload(Base):
    __tablename__ = "pending_uploads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SQL: char(36)
    token: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # SQL: kind varchar(16)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="document_upload")

    # SQL: target_document_id bigint unsigned
    target_document_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)

    # --- Alias Properties fuer bestehenden Code (purpose/context_doc_id) ---

    @property
    def purpose(self) -> str:
        return self.kind

    @purpose.setter
    def purpose(self, value: str) -> None:
        self.kind = value

    @property
    def context_doc_id(self) -> Optional[int]:
        return self.target_document_id

    @context_doc_id.setter
    def context_doc_id(self, value: Optional[int]) -> None:
        self.target_document_id = value
