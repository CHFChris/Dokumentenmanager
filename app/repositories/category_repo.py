# app/repositories/category_repo.py
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.category import Category


def list_categories_for_user(db: Session, user_id: int) -> List[Category]:
    return (
        db.query(Category)
        .filter(Category.user_id == user_id)
        .order_by(Category.name.asc())
        .all()
    )


def get_category_by_name(db: Session, user_id: int, name: str) -> Optional[Category]:
    return (
        db.query(Category)
        .filter(Category.user_id == user_id, Category.name == name)
        .first()
    )


def create_category(db: Session, user_id: int, name: str) -> Category:
    existing = get_category_by_name(db, user_id, name)
    if existing:
        return existing

    cat = Category(user_id=user_id, name=name.strip())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def rename_category(db: Session, user_id: int, category_id: int, new_name: str):
    cat = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == user_id
        )
        .first()
    )
    if cat:
        cat.name = new_name.strip()
        db.commit()
        db.refresh(cat)


def delete_category(db: Session, user_id: int, category_id: int):
    cat = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == user_id
        )
        .first()
    )
    if cat:
        db.delete(cat)
        db.commit()
