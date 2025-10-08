from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, BigInteger, SmallInteger, TIMESTAMP
from typing import Optional, List

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(SmallInteger, default=1)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # created_at/updated_at sind DB-Default; kein Python-Default nötig

    documents: Mapped[List["Document"]] = relationship(back_populates="owner")
