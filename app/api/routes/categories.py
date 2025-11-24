# app/api/routes/categories.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse
from starlette.requests import Request

from app.api.deps import get_current_user_web, get_current_user, CurrentUser
from app.db.database import get_db
from app.web.templates import templates

from app.repositories.category_repo import (
    list_categories_for_user,
    create_category_for_user,
    delete_category_for_user,
)

from app.models.user import User
from app.models.category import Category

from app.schemas.category import (
    CategoryKeywordSuggestionOut,
    CategoryKeywordsUpdateIn,
    CategoryOut,
)

from app.services.auto_tagging import suggest_keywords_for_category


router = APIRouter(prefix="/categories", tags=["categories"])


# ---------------------------------------------------------
# 1) Kategorien-Ansicht (User-only)
# ---------------------------------------------------------
@router.get("/")
def list_categories_view(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    categories = list_categories_for_user(db, user.id)
    return templates.TemplateResponse(
        "categories.html",
        {
            "request": request,
            "user": user,
            "categories": categories,
        },
    )


# ---------------------------------------------------------
# 2) Kategorie erstellen (User-only)
# ---------------------------------------------------------
@router.post("/create-web")
def create_category_view(
    name: str = Form(...),
    keywords: str | None = Form(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    try:
        create_category_for_user(db, user.id, name, keywords)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RedirectResponse(url="/categories", status_code=303)


# ---------------------------------------------------------
# 3) Kategorie löschen (User-only)
# ---------------------------------------------------------
@router.post("/{category_id}/delete-web")
def delete_category_view(
    category_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    ok = delete_category_for_user(db, user.id, category_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Category not found")

    return RedirectResponse(url="/categories", status_code=303)


# ---------------------------------------------------------
# 4) Keyword-Vorschläge für Kategorien (User-only)
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# 5) Keywords in Kategorie speichern (User-only)
# ---------------------------------------------------------
@router.patch("/{category_id}/keywords", response_model=CategoryOut)
def update_category_keywords(
    category_id: int,
    payload: CategoryKeywordsUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == current_user.id,  # Datenschutz
        )
        .first()
    )

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    cleaned = [k.strip() for k in payload.keywords if k.strip()]
    category.keywords = ", ".join(cleaned) if cleaned else None

    db.add(category)
    db.commit()
    db.refresh(category)

    return category
