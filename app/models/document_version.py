# app/models/document_version.py
from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DateTime, ForeignKey, BigInteger, func, UniqueConstraint

from app.db.database import Base  # <- richtige Base!

if TYPE_CHECKING:
    from app.models.document import Document  # nur für Typ-Hints, verhindert Zyklen


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uix_doc_version"),
    )

    # Wähle Integer ODER BigInteger – passend zu documents.id:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    document_id: Mapped[int] = mapped_column(
        Integer,  # falls dein Document.id BigInteger ist, hier auch BigInteger!
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Wichtig: Klassenname als String, kein Direktimport → kein Zyklus
    document: Mapped["Document"] = relationship("Document", back_populates="versions")

    def __repr__(self) -> str:
        return f"<DocumentVersion id={self.id} doc={self.document_id} v={self.version_number}>"
