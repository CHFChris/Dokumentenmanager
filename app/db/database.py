# app/db/database.py
from __future__ import annotations

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.core.config import settings


# === Declarative Base (SQLAlchemy 2.x) ===
class Base(DeclarativeBase):
    pass


# === Engine & Session ===
engine = create_engine(
    settings.DB_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)


# === Models registrieren (damit FKs bekannt sind) ===
def init_models() -> None:
    # sorgt dafür, dass alle Modelle (User, PasswordResetToken, etc.)
    # im Base.metadata registriert sind
    import app.models  # noqa: F401


# === DB-Session Dependency für FastAPI ===
def get_db() -> Generator[Session, None, None]:
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
