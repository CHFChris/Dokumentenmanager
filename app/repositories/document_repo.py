# app/repositories/document_repo.py
from __future__ import annotations

from typing import List, Tuple, Optional
from datetime import datetime, timedelta

from sqlalchemy import select, update, func, desc
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_version import DocumentVersion


# -------------------------------------------------------------------
# Gemeinsame Filter
# -------------------------------------------------------------------
def _filters(user_id: int, q: Optional[str]) -> list:
    """
    - filtert nach Besitzer und nicht-gelöschten Dokumenten
    - optional case-insensitive Suche im Dateinamen
    """
    cond = [Document.owner_user_id == user_id, Document.is_deleted.is_(False)]
    if q:
        like = f"%{q.lower()}%"
        cond.append(func.lower(Document.filename).like(like))
    return cond


# -------------------------------------------------------------------
# Suche / Listen
# -------------------------------------------------------------------
def search_documents(
    db: Session,
    user_id: int,
    q: Optional[str],
    limit: int,
    offset: int,
) -> Tuple[List[Document], int]:
    cond = _filters(user_id, q)

    stmt = (
        select(Document)
        .where(*cond)
        .order_by(Document.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows: List[Document] = db.execute(stmt).scalars().all()

    count_stmt = select(func.count()).select_from(Document).where(*cond)
    total: int = db.execute(count_stmt).scalar() or 0

    return rows, total


def list_documents_for_user(
    db: Session,
    user_id: int,
    q: Optional[str],
    limit: int,
    offset: int,
) -> Tuple[List[Document], int]:
    """
    Funktional identisch zu search_documents, bleibt für API-Kompatibilität separat.
    """
    return search_documents(db, user_id, q, limit, offset)


# -------------------------------------------------------------------
# Anlegen / Version
# -------------------------------------------------------------------
def create_document_with_version(
    db: Session,
    user_id: int,
    filename: str,
    storage_path: str,
    size_bytes: int,
    checksum_sha256: Optional[str],
    mime_type: Optional[str],
) -> Document:
    doc = Document(
        owner_user_id=user_id,
        filename=filename,
        storage_path=storage_path,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256,
        mime_type=mime_type or None,
    )
    db.add(doc)
    db.flush()  # doc.id ist jetzt verfügbar

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_path=storage_path,
        checksum_sha256=checksum_sha256,
    )
    db.add(ver)

    db.commit()
    db.refresh(doc)
    return doc


# -------------------------------------------------------------------
# Soft-Delete
# -------------------------------------------------------------------
def soft_delete_document(db: Session, doc_id: int, user_id: int) -> bool:
    res = db.execute(
        update(Document)
        .where(
            Document.id == doc_id,
            Document.owner_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        .values(is_deleted=True)
    )
    db.commit()
    return (res.rowcount or 0) > 0


# -------------------------------------------------------------------
# Dashboard-Stats / Recent Uploads
# -------------------------------------------------------------------
def count_documents_for_user(db: Session, user_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(Document)
        .where(Document.owner_user_id == user_id, Document.is_deleted.is_(False))
    )
    return int(db.execute(stmt).scalar() or 0)


def storage_used_for_user(db: Session, user_id: int) -> int:
    stmt = (
        select(func.coalesce(func.sum(Document.size_bytes), 0))
        .select_from(Document)
        .where(Document.owner_user_id == user_id, Document.is_deleted.is_(False))
    )
    return int(db.execute(stmt).scalar() or 0)


def recent_uploads_count_week(db: Session, user_id: int) -> int:
    """
    Zählt Uploads der letzten 7 Tage.
    Hat das Modell kein 'created_at', fällt die Zeitfilterung weg (liefert dann Gesamtzahl),
    damit es nicht crasht.
    """
    has_created_at = hasattr(Document, "created_at")
    if has_created_at:
        since = datetime.utcnow() - timedelta(days=7)
        stmt = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.owner_user_id == user_id,
                Document.is_deleted.is_(False),
                Document.created_at >= since,
            )
        )
        return int(db.execute(stmt).scalar() or 0)
    # Fallback ohne created_at
    return count_documents_for_user(db, user_id)


def recent_uploads_for_user(db: Session, user_id: int, limit: int = 5):
    """
    Liefert die letzten Uploads (für die Liste). Sortierung nach created_at, fallback id.
    Gibt template-freundliche Dicts zurück: {id, name, ext, created_at}.
    """
    has_created_at = hasattr(Document, "created_at")
    order_by_col = Document.created_at if has_created_at else Document.id

    stmt = (
        select(Document)
        .where(Document.owner_user_id == user_id, Document.is_deleted.is_(False))
        .order_by(desc(order_by_col))
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()

    items = []
    for d in rows:
        ext = d.filename.rsplit(".", 1)[-1].upper() if "." in d.filename else ""
        items.append(
            {
                "id": d.id,
                "name": d.filename,
                "ext": ext,
                "created_at": getattr(d, "created_at", None),
            }
        )
    return items
