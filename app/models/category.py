# app/models/category.py
from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class Category(Base):
    __tablename__ = "categories"

    # ------------------------------------------------------------
    # Core
    # ------------------------------------------------------------
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # Besitzer der Kategorie (User-spezifische Kategorien)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Anzeigename der Kategorie
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Freies Textfeld für Schlagwörter / Keywords (durch KI gepflegt)
    keywords: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # ------------------------------------------------------------
    # Beziehungen
    # ------------------------------------------------------------
    # User -> Kategorien (wird per backref am User als "categories" verfügbar)
    user: Mapped["User"] = relationship(
        "User",
        backref="categories",
    )

    # Kategorie -> Dokumente (Rückseite von Document.category)
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="category",
    )

    # ------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------
    @property
    def keyword_list(self) -> list[str]:
        """
        Hilfsproperty: Keywords als Liste.
        Trennt an Kommas und Zeilenumbrüchen, entfernt Leerzeichen.
        """
        if not self.keywords:
            return []
        raw = self.keywords.replace("\r", "\n")
        parts = [p.strip() for p in raw.replace(",", "\n").split("\n")]
        return [p for p in parts if p]

    @keyword_list.setter
    def keyword_list(self, values: list[str]) -> None:
        """
        Setzt keywords aus einer Liste; speichert sie kommasepariert.
        """
        self.keywords = ", ".join(v.strip() for v in values if v.strip())

    # ------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------
    def __repr__(self) -> str:
        return f"<Category id={self.id} user_id={self.user_id} name={self.name!r}>"
