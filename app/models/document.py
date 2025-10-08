from typing import Optional, List   # <-- NEU

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, BigInteger, SmallInteger, Integer, Boolean, ForeignKey
from app.models.user import Base, User

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    folder_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_provider_id: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    owner: Mapped[User] = relationship(back_populates="documents")
    versions: Mapped[List["DocumentVersion"]] = relationship(  # List importiert
        back_populates="document",
        cascade="all, delete-orphan"
    )
