# app/models/user.py
from __future__ import annotations
from typing import Optional, TYPE_CHECKING, List

from sqlalchemy import Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.document import Document  # nur für Typ-Hinweise


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Rollen: 1 = Standard, 2 = Admin (Beispiel)
    role_id: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    # Benutzername: Pflicht & eindeutig (Login oder Handle)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # E-Mail: Pflicht & eindeutig
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Passwort-Hash (z. B. Argon2 / bcrypt)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Optionaler Anzeigename
    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # Beziehungen
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} email={self.email!r} role_id={self.role_id}>"
