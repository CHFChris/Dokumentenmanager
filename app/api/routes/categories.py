# app/api/routes/categories.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse
from starlette.requests import Request

from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db
from app.repositories.category_repo import (
    list_categories_for_user,
    create_category_for_user,
    delete_category_for_user,
)
from app.models.category import Category

router = APIRouter(prefix="/categories", tags=["categories"])


# -------------------------------------------------
# Redirect auf neue Oberfläche /category-keywords
# -------------------------------------------------
@router.get("/")
def list_categories_view(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    return RedirectResponse(url="/category-keywords", status_code=303)


# -------------------------------------------------
# Kategorie anlegen -> danach auf /category-keywords
# -------------------------------------------------
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

    return RedirectResponse(url="/category-keywords", status_code=303)


# -------------------------------------------------
# Kategorie löschen -> ebenfalls /category-keywords
# -------------------------------------------------
@router.post("/{category_id}/delete-web")
def delete_category_view(
    category_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    ok = delete_category_for_user(db, user.id, category_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Category not found")

    return RedirectResponse(url="/documents", status_code=303)
