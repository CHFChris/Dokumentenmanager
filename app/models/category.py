# app/models/category.py
from __future__ import annotations

from typing import List, TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, ForeignKey

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Nutzer besitzt Kategorien
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Beziehung: eine Kategorie hat mehrere Dokumente
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="category",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # optional, falls User -> categories benötigt wird
    # user: Mapped["User"] = relationship("User", back_populates="categories")

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r}>"
