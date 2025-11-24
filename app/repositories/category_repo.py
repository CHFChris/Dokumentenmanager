# app/repositories/category_repo.py
from __future__ import annotations

from typing import Optional, List

from sqlalchemy.orm import Session

from app.models.category import Category


def list_categories_for_user(
    db: Session,
    user_id: int,
) -> List[Category]:
    """
    Liefert alle Kategorien eines Users.
    Andere User sehen diese Kategorien nicht.
    """
    return (
        db.query(Category)
        .filter(Category.user_id == user_id)
        .order_by(Category.name.asc())
        .all()
    )


def get_category_for_user(
    db: Session,
    user_id: int,
    category_id: int,
) -> Optional[Category]:
    """
    Holt genau eine Kategorie, aber nur,
    wenn sie dem User gehört.
    """
    return (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == user_id,
        )
        .one_or_none()
    )


def create_category_for_user(
    db: Session,
    user_id: int,
    name: str,
    keywords: Optional[str] = None,
) -> Category:
    """
    Legt eine neue Kategorie für den User an.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Name darf nicht leer sein")

    cat = Category(
        user_id=user_id,
        name=name,
        keywords=keywords or None,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def delete_category_for_user(
    db: Session,
    user_id: int,
    category_id: int,
) -> bool:
    """
    Löscht eine Kategorie nur, wenn sie dem User gehört.
    """
    cat = get_category_for_user(db, user_id, category_id)
    if not cat:
        return False

    db.delete(cat)
    db.commit()
    return True
