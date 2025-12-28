# app/models/category.py
from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.document_categories import document_categories
from app.utils.crypto_utils import encrypt_text, decrypt_text

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    _keywords: Mapped[Optional[str]] = mapped_column(
        "keywords",
        Text,
        nullable=True,
    )

    # Many-to-Many: exklusiv (alte Single-Category Beziehung entfernt)
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        secondary=document_categories,
        back_populates="categories",
        lazy="selectin",
    )

    user: Mapped["User"] = relationship(
        "User",
        lazy="selectin",
    )

    @property
    def keywords(self) -> str:
        if not self._keywords:
            return ""
        try:
            return decrypt_text(self._keywords)
        except Exception:
            return self._keywords

    @keywords.setter
    def keywords(self, value: str) -> None:
        text = (value or "").strip()
        if not text:
            self._keywords = None
        else:
            self._keywords = encrypt_text(text)

    def __repr__(self) -> str:
        return f"<Category id={self.id} user_id={self.user_id} name={self.name!r}>"
