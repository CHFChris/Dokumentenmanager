# app/models/document_categories.py
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Table, func
from sqlalchemy.dialects.mysql import BIGINT

from app.db.database import Base

document_categories = Table(
    "document_categories",
    Base.metadata,
    Column(
        "document_id",
        BIGINT(unsigned=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        BIGINT(unsigned=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
)
