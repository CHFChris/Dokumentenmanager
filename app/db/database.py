from __future__ import annotations
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.core.config import settings


class Base(DeclarativeBase):
    pass


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


def init_models() -> None:
    # Registriert alle Models in Base.metadata
    import app.models  # noqa: F401


def get_db() -> Generator[Session, None, None]:
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
