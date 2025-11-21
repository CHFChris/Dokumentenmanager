# app/schemas/category.py
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


# Basismodell (gemeinsame Felder)
class CategoryBase(BaseModel):
    name: str
    keywords: Optional[str] = None  # kommaseparierte Keywords, optional


# Schema: Kategorie erstellen
class CategoryCreate(CategoryBase):
    pass


# Schema: Kategorie aktualisieren
class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    keywords: Optional[str] = None


# Schema: Kategorie ausgeben
class CategoryOut(CategoryBase):
    id: int
    user_id: int

    class Config:
        orm_mode = True


# Antwort für das KI-Keyword-Feature
class CategoryKeywordSuggestionOut(BaseModel):
    category_id: int
    category_name: str
    existing_keywords: List[str]
    suggested_keywords: List[str]

class CategoryKeywordsUpdateIn(BaseModel):
    keywords: List[str]
