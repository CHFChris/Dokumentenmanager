# app/models/document_version.py
from __future__ import annotations
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, Integer, String, DateTime, ForeignKey, func, UniqueConstraint

from app.models.user import Base
from app.models.document import Document

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uix_doc_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # z. B. „Titel geändert“, „Inhalt ersetzt“, „automatische Versionierung“
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    # Beziehungen
    document: Mapped[Document] = relationship(back_populates="versions")

    def __repr__(self) -> str:
        return f"<DocumentVersion id={self.id} doc={self.document_id} v={self.version_number}>"
