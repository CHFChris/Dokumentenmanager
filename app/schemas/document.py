# app/schemas/document.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    name: str
    size: int
    sha256: str
    created_at: Optional[datetime] = None

    # legacy (kommagetrennt)
    category: Optional[str] = None

    # neu
    category_ids: List[int] = []
    category_names: List[str] = []

    class Config:
        from_attributes = True


class DocumentListOut(BaseModel):
    items: List[DocumentOut]
    total: int

    class Config:
        from_attributes = True
