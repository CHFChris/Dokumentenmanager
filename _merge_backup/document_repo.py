# app/repositories/document_repo.py
from __future__ import annotations

from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timedelta

<<<<<<< HEAD
from sqlalchemy import select, update, func, desc
=======
from sqlalchemy import select, update, func, desc, or_
>>>>>>> backup/feature-snapshot
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.utils.crypto_utils import encrypt_text  # für verschlüsselte OCR-Texte


# -------------------------------------------------------------------
# Hilfsfunktion: Owner-Filter + Textsuche
# -------------------------------------------------------------------
def _filters(user_id: int, q: Optional[str]) -> list:
    """
    Gemeinsamer Filter:
    - Nur Dokumente des Users
    - Nur nicht-gelöschte
    - Optional case-insensitive Suche im Dateinamen
    """
    cond = [Document.owner_user_id == user_id, Document.is_deleted.is_(False)]
    if q:
        like = f"%{q.lower()}%"
        cond.append(func.lower(Document.filename).like(like))
    return cond


# -------------------------------------------------------------------
# Einzelabrufe / Owner-Check
# -------------------------------------------------------------------
def get_document_for_user(db: Session, user_id: int, doc_id: int) -> Optional[Document]:
    """
    Holt GENAU EIN Dokument für den gegebenen User (nur nicht-gelöschte).
    Gibt None zurück, wenn nicht vorhanden oder nicht berechtigt.
    Eager-load: Kategorien (Many-to-Many).
    """
    stmt = (
        select(Document)
        .where(
            Document.id == doc_id,
            Document.owner_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        .options(selectinload(Document.categories))
        .limit(1)
    )
    return db.execute(stmt).scalars().one_or_none()


def get_document_owned(db: Session, doc_id: int, owner_id: int) -> Optional[Document]:
    """
    Rückwärtskompatibler Wrapper für Altcode.
    Neu bitte `get_document_for_user(db, user_id, doc_id)` verwenden.
    """
    return get_document_for_user(db=db, user_id=owner_id, doc_id=doc_id)


# -------------------------------------------------------------------
# Umbenennen (nur DB, verschiebt KEINE Dateien im FS/Storage)
# -------------------------------------------------------------------
def rename_document(db: Session, user_id: int, doc_id: int, new_name: str) -> bool:
    """
    Bennennt ein Dokument um (nur Owner & nicht gelöscht).
    Rückgabe: True bei Erfolg, sonst False.
    """
    new_name = (new_name or "").strip()
    if not new_name:
        return False

    # Minimaler Basisschutz gegen unzulässige Namen/Steuerzeichen
    if any(ch in new_name for ch in ("/", "\\", "\0")):
        return False

    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        return False

    doc.filename = new_name

    # Optional: updated_at pflegen, falls Feld existiert
    if hasattr(doc, "updated_at"):
        try:
            doc.updated_at = datetime.utcnow()
        except Exception:
            pass

    db.commit()
    db.refresh(doc)
    return True


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
    Liefert (Dokumentenliste, Gesamtanzahl).
    Sortierung: Neueste zuerst (nach created_at, sonst id).
    Eager-load: Kategorien (Many-to-Many).
    """
    cond = _filters(user_id, q)

    has_created_at = hasattr(Document, "created_at")
    order_by_col = Document.created_at if has_created_at else Document.id

    stmt = (
        select(Document)
        .where(*cond)
        .options(selectinload(Document.categories))
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
# Anlegen + erste Version (vereinigte Variante MIT note + Zusatzfeldern)
# -------------------------------------------------------------------
def create_document_with_version(
    db: Session,
    user_id: int,
    filename: str,
    storage_path: str,
    size_bytes: int,
    checksum_sha256: Optional[str],
    mime_type: Optional[str],
    note: Optional[str] = None,
    original_filename: Optional[str] = None,
    stored_name: Optional[str] = None,
) -> Document:
    """
    Legt ein Document an und erzeugt Version 1 (inkl. optionaler Notiz).
    - Spiegelt initiale Metadaten in Document und DocumentVersion.
    - `note` defaulted auf "Initial upload", wenn None oder leer.

    Zusatzfelder (Metadaten):
    - original_filename: Anzeigename/Originalname (z. B. fuer Download/Preview)
    - stored_name: interner eindeutiger Dateiname (Unique Key) fuer Storage
    """
    doc = Document(
        owner_user_id=user_id,
        filename=filename,
        storage_path=storage_path,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256 or None,
        mime_type=mime_type or None,
        original_filename=original_filename or None,
        stored_name=stored_name or None,
    )
    db.add(doc)
    db.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_path=storage_path,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256 or None,
        mime_type=mime_type or None,
        note=(note or "Initial upload"),
    )
    db.add(ver)

    db.commit()
    db.refresh(doc)
    return doc


# -------------------------------------------------------------------
# Soft-Delete (Markierung)
# -------------------------------------------------------------------
def soft_delete_document(db: Session, doc_id: int, user_id: int) -> bool:
    """
    Markiert ein Dokument als gelöscht (soft).
    True, wenn genau eine Zeile betroffen ist.
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


# -------------------------------------------------------------------
# Atomare Aktualisierung von Name + Pfad
# -------------------------------------------------------------------
def update_document_name_and_path(
    db: Session,
    user_id: int,
    doc_id: int,
    new_filename: str,
    new_storage_path: str,
) -> bool:
    """
    Aktualisiert atomar filename + storage_path (nur wenn Owner & nicht gelöscht).
    Rückgabe: True, wenn genau eine Zeile aktualisiert wurde.
    """
    new_filename = (new_filename or "").strip()
    new_storage_path = (new_storage_path or "").strip()
    if not new_filename or not new_storage_path:
        return False

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
    Sortierung nach created_at, Fallback id.
    Rückgabe als template-freundliche Dicts.
    Eager-load: Kategorien (damit Dashboard/Listen nicht nachladen).
    """
    has_created_at = hasattr(Document, "created_at")
    order_by_col = Document.created_at if has_created_at else Document.id

    stmt = (
        select(Document)
        .where(Document.owner_user_id == user_id, Document.is_deleted.is_(False))
        .options(selectinload(Document.categories))
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
                "name": d.filename,
                "ext": ext,
                "created_at": getattr(d, "created_at", None),
                "categories": getattr(d, "categories", []) or [],
            }
        )
    return items


# -------------------------------------------------------------------
# Versionierung
# -------------------------------------------------------------------
def list_versions_for_document(db: Session, doc_id: int, owner_id: int) -> List[DocumentVersion]:
    sub = (
        select(Document.id)
        .where(
            Document.id == doc_id,
            Document.owner_user_id == owner_id,
            Document.is_deleted.is_(False),
        )
        .scalar_subquery()
    )

    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == sub)
        .order_by(desc(DocumentVersion.version_number))
    )
    return db.execute(stmt).scalars().all()


def next_version_number(db: Session, doc_id: int) -> int:
    stmt = select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
        DocumentVersion.document_id == doc_id
    )
    return (db.scalar(stmt) or 0) + 1


def add_version(
    db: Session,
    doc: Document,
    storage_path: str,
    size_bytes: int,
    checksum_sha256: Optional[str],
    mime_type: Optional[str],
    note: Optional[str],
) -> DocumentVersion:
    vnum = next_version_number(db, doc.id)

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=vnum,
        storage_path=storage_path,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256 or None,
        mime_type=mime_type or None,
        note=note,
    )
    db.add(ver)

    db.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(
            storage_path=storage_path,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256 or None,
            mime_type=mime_type or None,
        )
    )

    db.commit()
    db.refresh(ver)
    db.refresh(doc)
    return ver


def get_version_owned(db: Session, doc_id: int, version_id: int, owner_id: int) -> Optional[DocumentVersion]:
    ver_stmt = (
        select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == doc_id,
            Document.owner_user_id == owner_id,
            Document.is_deleted.is_(False),
        )
        .limit(1)
    )
    return db.execute(ver_stmt).scalar_one_or_none()


# -------------------------------------------------------------------
# OCR-Schreiben (verschlüsselt)
# -------------------------------------------------------------------
def set_ocr_text_for_document(
    db: Session,
    user_id: int,
    doc_id: int,
    ocr_plaintext: Optional[str],
) -> bool:
    text = (ocr_plaintext or "").strip()
    encrypted = encrypt_text(text) if text else None

    res = db.execute(
        update(Document)
        .where(
            Document.id == doc_id,
            Document.owner_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        .values(ocr_text=encrypted)
    )
    db.commit()
    return (res.rowcount or 0) > 0


# -------------------------------------------------------------------
# Duplikate: SHA256 oder (Name + Groesse)
# -------------------------------------------------------------------
def get_by_sha_or_name_size(
    db: Session,
    user_id: int,
    sha256: Optional[str],
    filename: Optional[str],
    size_bytes: Optional[int],
) -> Optional[Document]:
    """Findet ein bereits vorhandenes Dokument des Users.

    Trefferregeln:
    1) checksum_sha256 == sha256 (falls sha256 gesetzt)
    2) filename (case-insensitive) + size_bytes (falls beides gesetzt)

    Rueckgabe: Document oder None.
    """
    sha256 = (sha256 or "").strip()
    filename = (filename or "").strip()

    try:
        size_val = int(size_bytes) if size_bytes is not None else None
    except Exception:
        size_val = None

    if not sha256 and (not filename or size_val is None):
        return None

    name_size_block = None
    if filename and size_val is not None:
        name_size_block = (func.lower(Document.filename) == func.lower(filename)) & (Document.size_bytes == size_val)

    if sha256 and name_size_block is not None:
        match_expr = or_(Document.checksum_sha256 == sha256, name_size_block)
    elif sha256:
        match_expr = (Document.checksum_sha256 == sha256)
    else:
        match_expr = name_size_block

    stmt = (
        select(Document)
        .where(
            Document.owner_user_id == user_id,
            Document.is_deleted.is_(False),
            match_expr,
        )
        .order_by(desc(Document.id))
        .limit(1)
    )
    return db.execute(stmt).scalars().one_or_none()
