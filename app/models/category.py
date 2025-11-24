# app/models/category.py
from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
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

    # muss zum Typ von users.id passen (nach deiner Migration: Integer)
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

    # physische DB-Spalte bleibt "keywords"
    # im Code heißt das Attribut _keywords (intern, verschlüsselt)
    _keywords: Mapped[Optional[str]] = mapped_column(
        "keywords",
        Text,
        nullable=True,
    )

    # Beziehungen
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="category",
        lazy="selectin",
    )

    user: Mapped["User"] = relationship(
        "User",
        lazy="selectin",
    )

    # ---------------------------------------
    # Property: arbeitet mit KLARTEXT
    # ---------------------------------------
    @property
    def keywords(self) -> str:
        """
        Gibt die Keywords als Klartext zurück.
        In der DB liegt verschlüsselter Text in self._keywords.
        """
        if not self._keywords:
            return ""
        try:
            return decrypt_text(self._keywords)
        except Exception:
            # Fallback: falls alte Daten noch unverschlüsselt sind
            return self._keywords

    @keywords.setter
    def keywords(self, value: str) -> None:
        """
        Nimmt Klartext entgegen und speichert verschlüsselt in self._keywords.
        """
        text = (value or "").strip()
        if not text:
            self._keywords = None
        else:
            self._keywords = encrypt_text(text)

    def __repr__(self) -> str:
        return f"<Category id={self.id} user_id={self.user_id} name={self.name!r}>"
