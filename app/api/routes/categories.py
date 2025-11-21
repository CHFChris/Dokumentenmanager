# app/api/routes/categories.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.category import CategoryKeywordSuggestionOut
from app.services.auto_tagging import suggest_keywords_for_category

from app.schemas.category import (
    CategoryKeywordSuggestionOut,
    CategoryKeywordsUpdateIn,
    CategoryOut,  # falls noch nicht importiert
)
from app.models.category import Category


router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/{category_id}/keyword-suggestions", response_model=CategoryKeywordSuggestionOut)
def get_category_keyword_suggestions(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = suggest_keywords_for_category(
            db=db,
            user_id=current_user.id,
            category_id=category_id,
            top_n=15,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Category not found")

    return result

@router.patch("/{category_id}/keywords", response_model=CategoryOut)
def update_category_keywords(
    category_id: int,
    payload: CategoryKeywordsUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Kategorie laden und Ownership prüfen
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == current_user.id,
        )
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Liste -> kommaseparierter String
    cleaned = [k.strip() for k in payload.keywords if k.strip()]
    category.keywords = ", ".join(cleaned) if cleaned else None

    db.add(category)
    db.commit()
    db.refresh(category)

    return category

