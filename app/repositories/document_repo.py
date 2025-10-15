# app/repositories/document_repo.py
from __future__ import annotations

from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select, update, func, desc
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_version import DocumentVersion


# -------------------------------------------------------------------
# Einzeldokument (Owner-Check)
# -------------------------------------------------------------------
def get_document_for_user(db: Session, user_id: int, doc_id: int) -> Optional[Document]:
    """
    Holt genau EIN Dokument für den gegebenen User (nur nicht-gelöschte).
    """
    stmt = (
        select(Document)
        .where(
            Document.id == doc_id,
            Document.owner_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        .limit(1)
    )
    return db.execute(stmt).scalars().one_or_none()


# Rückwärtskompatibel: alter Name/Signatur
def get_document_owned(db: Session, doc_id: int, owner_id: int) -> Optional[Document]:
    """
    Altkompatibler Wrapper – bitte neu: get_document_for_user(db, user_id, doc_id)
    """
    return get_document_for_user(db=db, user_id=owner_id, doc_id=doc_id)


# -------------------------------------------------------------------
# Rename
# -------------------------------------------------------------------
def rename_document(db: Session, user_id: int, doc_id: int, new_name: str) -> bool:
    """
    Bennennt ein Dokument um (nur Owner & nicht gelöscht). True bei Erfolg.
    """
    new_name = (new_name or "").strip()
    if not new_name:
        return False

    # Basisschutz gegen unzulässige Namen / Steuerzeichen
    if any(ch in new_name for ch in ("/", "\\", "\0")):
        return False

    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        return False

    doc.filename = new_name

    # Optional: updated_at pflegen, falls im Modell vorhanden
    if hasattr(doc, "updated_at"):
        try:
            doc.updated_at = datetime.utcnow()
        except Exception:
            pass

    db.commit()
    db.refresh(doc)
    return True


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
    """
    Gibt (Dokumente, Gesamtzahl) zurück. Sortiert neueste zuerst.
    """
    cond = _filters(user_id, q)

    # Nach created_at, sonst fallback id
    has_created_at = hasattr(Document, "created_at")
    order_by_col = Document.created_at if has_created_at else Document.id

    stmt = (
        select(Document)
        .where(*cond)
        .order_by(desc(order_by_col))
        .limit(limit)
        .offset(offset)
    )
    rows: List[Document] = db.execute(stmt).scalars().all()

    total_stmt = select(func.count()).select_from(Document).where(*cond)
    total: int = int(db.execute(total_stmt).scalar() or 0)

    return rows, total


def list_documents_for_user(
    db: Session,
    user_id: int,
    q: Optional[str],
    limit: int,
    offset: int,
) -> Tuple[List[Document], int]:
    """
    Alias zu search_documents – bleibt separat für API-Kompatibilität.
    """
    return search_documents(db, user_id, q, limit, offset)


# -------------------------------------------------------------------
# Anlegen + erste Version
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
    """
    Legt ein Document an und erzeugt Version 1.
    """
    doc = Document(
        owner_user_id=user_id,
        filename=filename,
        storage_path=storage_path,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256 or None,
        mime_type=mime_type or None,
    )
    db.add(doc)
    db.flush()  # doc.id verfügbar

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_path=storage_path,
        checksum_sha256=checksum_sha256 or None,
    )
    db.add(ver)

    db.commit()
    db.refresh(doc)
    return doc


# -------------------------------------------------------------------
# Soft-Delete
# -------------------------------------------------------------------
def soft_delete_document(db: Session, doc_id: int, user_id: int) -> bool:
    """
    Markiert ein Dokument als gelöscht (soft). True, wenn genau eine Zeile betroffen ist.
    """
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


# Atomare Aktualisierung von Name + Pfad
def update_document_name_and_path(
    db: Session,
    user_id: int,
    doc_id: int,
    new_filename: str,
    new_storage_path: str,
) -> bool:
    """
    Aktualisiert atomar filename + storage_path (nur wenn Owner & nicht gelöscht).
    True, wenn genau eine Zeile aktualisiert wurde.
    """
    new_filename = (new_filename or "").strip()
    new_storage_path = (new_storage_path or "").strip()
    if not new_filename or not new_storage_path:
        return False

    # Basisschutz gegen Pfad-Trenner im filename
    if any(ch in new_filename for ch in ("/", "\\", "\0")):
        return False

    res = db.execute(
        update(Document)
        .where(
            Document.id == doc_id,
            Document.owner_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        .values(filename=new_filename, storage_path=new_storage_path)
    )
    db.commit()
    return (res.rowcount or 0) > 0


# -------------------------------------------------------------------
# Dashboard-Stats
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
    Fällt ohne created_at auf Gesamtzahl zurück.
    """
    if hasattr(Document, "created_at"):
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
    return count_documents_for_user(db, user_id)


def recent_uploads_for_user(db: Session, user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Liefert die letzten Uploads (für das Dashboard).
    Sortiert nach created_at, fallback id. Template-freundliche Dicts.
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

    items: List[Dict[str, Any]] = []
    for d in rows:
        ext = d.filename.rsplit(".", 1)[-1].upper() if "." in d.filename else ""
        items.append(
            {
                "id": d.id,
                "name": d.filename,  # bewusst "name" für Template-Kompatibilität
                "ext": ext,
                "created_at": getattr(d, "created_at", None),
            }
        )
    return items
