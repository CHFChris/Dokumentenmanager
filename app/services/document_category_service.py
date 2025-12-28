# app/services/document_category_service.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.category import Category


def set_document_categories(db: Session, doc_id: int, user_id: int, category_ids: list[int]) -> None:
    doc = db.scalar(select(Document).where(Document.id == doc_id, Document.owner_user_id == user_id))
    if not doc:
        raise ValueError("Document not found or not owned by user")

    if category_ids:
        cats = db.scalars(
            select(Category).where(Category.user_id == user_id, Category.id.in_(category_ids))
        ).all()
    else:
        cats = []

    doc.categories = cats

    # Optional: falls deine DB noch documents.category_id hat und alter Code darauf schaut
    if hasattr(doc, "category_id"):
        doc.category_id = cats[0].id if cats else None

    db.commit()


def bulk_set_document_categories(db: Session, doc_ids: list[int], user_id: int, category_ids: list[int]) -> None:
    docs = db.scalars(
        select(Document).where(
            Document.owner_user_id == user_id,
            Document.id.in_(doc_ids),
        )
    ).all()

    if not docs:
        return

    if category_ids:
        cats = db.scalars(
            select(Category).where(Category.user_id == user_id, Category.id.in_(category_ids))
        ).all()
    else:
        cats = []

    for d in docs:
        d.categories = cats

        # Optional legacy fallback
        if hasattr(d, "category_id"):
            d.category_id = cats[0].id if cats else None

    db.commit()
