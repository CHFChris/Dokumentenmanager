from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.models.document import Document


def _get_owned_document_or_none(
    db: Session,
    *,
    document_id: int,
    owner_user_id: int,
) -> Optional[Document]:
    stmt = (
        select(Document)
        .where(Document.id == document_id)
        .where(Document.owner_user_id == owner_user_id)
        .where(Document.is_deleted.is_(False))
    )
    return db.execute(stmt).scalar_one_or_none()


def set_favorite(
    db: Session,
    *,
    document_id: int,
    owner_user_id: int,
    is_favorite: bool,
) -> Document:
    doc = _get_owned_document_or_none(db, document_id=document_id, owner_user_id=owner_user_id)
    if doc is None:
        raise ValueError("DOCUMENT_NOT_FOUND_OR_NOT_OWNED")

    doc.is_favorite = bool(is_favorite)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def toggle_favorite(
    db: Session,
    *,
    document_id: int,
    owner_user_id: int,
) -> Document:
    doc = _get_owned_document_or_none(db, document_id=document_id, owner_user_id=owner_user_id)
    if doc is None:
        raise ValueError("DOCUMENT_NOT_FOUND_OR_NOT_OWNED")

    doc.is_favorite = not bool(doc.is_favorite)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def list_favorite_documents(
    db: Session,
    *,
    owner_user_id: int,
    limit: int = 50,
    offset: int = 0,
) -> List[Document]:
    stmt = (
        select(Document)
        .where(Document.owner_user_id == owner_user_id)
        .where(Document.is_deleted.is_(False))
        .where(Document.is_favorite.is_(True))
        .order_by(desc(Document.created_at), desc(Document.id))
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())
