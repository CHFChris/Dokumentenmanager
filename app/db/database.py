# app/db/database.py
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

DATABASE_URL = settings.DB_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_models() -> None:
    import app.models.user  # noqa: F401
    import app.models.category  # noqa: F401
    import app.models.document  # noqa: F401
    import app.models.document_version  # noqa: F401
    import app.models.document_categories  # noqa: F401
    import app.models.email_verification_token  # noqa: F401
    import app.models.password_reset_token  # noqa: F401
