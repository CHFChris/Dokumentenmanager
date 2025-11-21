# app/services/document_service.py
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import BinaryIO, Optional, List, Dict

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from app.core.config import settings
from app.models.document import Document
from app.repositories.document_repo import (
    # Dashboard
    count_documents_for_user,
    storage_used_for_user,
    recent_uploads_count_week,
    recent_uploads_for_user,
    # Documents
    create_document_with_version,
    soft_delete_document,
    get_document_for_user,          # neue, einheitliche Getter-API
    update_document_name_and_path,  # atomare DB-Aktualisierung
    # Legacy-Kompatibilität (nur für Wrapper unten verwendet):
    get_document_owned as _get_document_owned_legacy,
)
from app.schemas.document import DocumentListOut, DocumentOut
from app.utils.files import ensure_dir, save_stream_to_file, sha256_of_stream
from app.services.ocr_service import (
    extract_text_from_pdf,
    extract_text_from_image,
    extract_text_from_docx,
)
from app.services.auto_tagging import guess_category_for_text

# ------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------
FILES_DIR = getattr(settings, "FILES_DIR", "./data/files")

# sehr einfache Stopwort-Liste (de + en), für Tokenisierung
SIMPLE_STOPWORDS = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einer", "einem", "einen",
    "den", "im", "in", "ist", "sind", "war", "waren", "von", "mit", "auf", "für",
    "an", "am", "als", "zu", "zum", "zur", "bei", "aus", "dem",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "at", "by",
    "this", "that", "these", "those", "it", "its", "be", "was", "were", "are",
}


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _sanitize_display_name(name: str) -> str:
    """
    Bereinigt den vom User kommenden Anzeigenamen (für DB/UI).
    - entfernt Pfadangaben
    - ersetzt verbotene Zeichen
    - begrenzt Länge (255)
    """
    name = (name or "").strip()
    name = os.path.basename(name)
    bad = {"/", "\\", "\0"}
    if any(ch in name for ch in bad):
        name = name.replace("/", "_").replace("\\", "_").replace("\0", "")
    return name[:255] or "unnamed"


def _uuid_disk_name_with_ext(original_name: str) -> str:
    """
    Erzeugt einen eindeutigen Dateinamen für die Festplatte:
    <uuid>.<ext> (Extension aus Originalname, lowercased)
    """
    _, ext = os.path.splitext(original_name or "")
    ext = ext.lower()
    return f"{uuid.uuid4().hex}{ext}"


def _unique_target_path(base_dir: str, original_name_for_ext: str) -> tuple[str, str]:
    """
    Liefert (disk_name, target_path) für einen kollisionsfreien Zielpfad.
    Nutzt UUID + Original-Extension.
    """
    ensure_dir(base_dir)
    disk_name = _uuid_disk_name_with_ext(original_name_for_ext)
    target_path = os.path.join(base_dir, disk_name)
    while os.path.exists(target_path):
        disk_name = _uuid_disk_name_with_ext(original_name_for_ext)
        target_path = os.path.join(base_dir, disk_name)
    return disk_name, target_path


def _tokenize(text: str) -> List[str]:
    """
    Sehr einfache Tokenisierung:
    - lowercasing
    - split auf whitespace
    - Filter: Länge >= 3, kein reines Sonderzeichen, keine Stopwörter
    """
    if not text:
        return []
    raw_tokens = text.lower().split()
    tokens: List[str] = []
    for t in raw_tokens:
        t = t.strip(".,;:!?()[]{}\"'`<>|/\\+-=_")
        if not t:
            continue
        if len(t) < 3:
            continue
        if t in SIMPLE_STOPWORDS:
            continue
        tokens.append(t)
    return tokens


def _score_document(title: str, body: str, query_tokens: List[str]) -> int:
    """
    Sehr einfache Relevanzbewertung:
    - Vorkommen im Titel mit Gewicht 3
    - Vorkommen im OCR-Text mit Gewicht 1
    """
    if not query_tokens:
        return 0

    title_l = (title or "").lower()
    body_l = (body or "").lower()

    score = 0
    for tok in query_tokens:
        if tok in title_l:
            score += 3
        if tok in body_l:
            score += 1
    return score


# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------
def dashboard_stats(db: Session, user_id: int) -> dict:
    total = count_documents_for_user(db, user_id)
    storage = storage_used_for_user(db, user_id)
    recent_week = recent_uploads_count_week(db, user_id)
    recent_items = recent_uploads_for_user(db, user_id, limit=5)

    # OCR-Wortstatistik für alle Dokumente mit OCR-Text
    most_words = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.ocr_text.isnot(None),
        )
        .all()
    )

    word_stats = [
        {
            "id": d.id,
            "words": len(d.ocr_text.split()) if d.ocr_text else 0,
        }
        for d in most_words
    ]

    return {
        "total": total,
        "storage_bytes": storage,
        "recent_week": recent_week,
        "recent_items": recent_items,
        "word_stats": word_stats,
    }


# ------------------------------------------------------------
# Listing / Suche (einfach, LIKE-basiert)
# ------------------------------------------------------------
def list_documents(
    db: Session,
    user_id: int,
    q: Optional[str],
    limit: int,
    offset: int,
    category_id: Optional[int] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    mime_startswith: Optional[str] = None,  # "image/", "application/pdf"
    only_with_ocr: bool = False,
) -> DocumentListOut:
    """
    EINFACHE Suche:
    - WHERE filename ILIKE ... OR ocr_text ILIKE ...
    - klassische Paginierung in der DB
    """
    query = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.is_deleted == False,  # noqa: E712
        )
    )

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            sa.or_(
                Document.filename.ilike(pattern),
                Document.ocr_text.ilike(pattern),
            )
        )

    if category_id is not None:
        query = query.filter(Document.category_id == category_id)

    if created_from is not None:
        query = query.filter(Document.created_at >= created_from)

    if created_to is not None:
        query = query.filter(Document.created_at <= created_to)

    if mime_startswith:
        query = query.filter(Document.mime_type.like(f"{mime_startswith}%"))

    if only_with_ocr:
        query = query.filter(Document.ocr_text.isnot(None))

    total = query.count()

    rows = (
        query.order_by(Document.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        DocumentOut(
            id=r.id,
            name=r.filename,
            size=r.size_bytes,
            sha256=(r.checksum_sha256 or ""),
            created_at=getattr(r, "created_at", None),
            category=(r.category.name if getattr(r, "category", None) else None),
        )
        for r in rows
    ]
    return DocumentListOut(items=items, total=total)


# ------------------------------------------------------------
# Erweiterte Suche (Tokenisierung + Relevanzranking)
# ------------------------------------------------------------
def search_documents_advanced(
    db: Session,
    user_id: int,
    q: str,
    limit: int,
    offset: int,
    category_id: Optional[int] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    mime_startswith: Optional[str] = None,
    only_with_ocr: bool = False,
) -> DocumentListOut:
    """
    ERWEITERTE Suche:
    - Tokenisierung der Query
    - Filter wie bei list_documents
    - Relevanzbewertung in Python
        * Titel wichtiger als OCR-Text
        * Sortierung nach Score DESC, dann created_at DESC
    - Paginierung NACH dem Ranking (Python-slicing)
    """
    if not q:
        return list_documents(
            db=db,
            user_id=user_id,
            q=None,
            limit=limit,
            offset=offset,
            category_id=category_id,
            created_from=created_from,
            created_to=created_to,
            mime_startswith=mime_startswith,
            only_with_ocr=only_with_ocr,
        )

    query_tokens = _tokenize(q)
    if not query_tokens:
        return DocumentListOut(items=[], total=0)

    base_query = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.is_deleted == False,  # noqa: E712
        )
    )

    if category_id is not None:
        base_query = base_query.filter(Document.category_id == category_id)

    if created_from is not None:
        base_query = base_query.filter(Document.created_at >= created_from)

    if created_to is not None:
        base_query = base_query.filter(Document.created_at <= created_to)

    if mime_startswith:
        base_query = base_query.filter(Document.mime_type.like(f"{mime_startswith}%"))

    if only_with_ocr:
        base_query = base_query.filter(Document.ocr_text.isnot(None))

    candidates: List[Document] = base_query.all()

    scored: List[Dict] = []
    for d in candidates:
        title = d.filename or ""
        body = d.ocr_text or ""
        score = _score_document(title, body, query_tokens)
        if score <= 0:
            continue
        scored.append({"doc": d, "score": score})

    scored.sort(
        key=lambda x: (
            x["score"],
            getattr(x["doc"], "created_at", datetime.min),
            x["doc"].id,
        ),
        reverse=True,
    )

    total = len(scored)
    sliced = scored[offset : offset + limit]

    items = [
        DocumentOut(
            id=entry["doc"].id,
            name=entry["doc"].filename,
            size=entry["doc"].size_bytes,
            sha256=(entry["doc"].checksum_sha256 or ""),
            created_at=getattr(entry["doc"], "created_at", None),
            category=(
                entry["doc"].category.name
                if getattr(entry["doc"], "category", None)
                else None
            ),
        )
        for entry in sliced
    ]

    return DocumentListOut(items=items, total=total)


# ------------------------------------------------------------
# Upload (mit optionaler Kategorie + OCR + Auto-Tagging)
# ------------------------------------------------------------
def upload_document(
    db: Session,
    user_id: int,
    original_name: str,
    file_obj: BinaryIO,
    category_id: Optional[int] = None,
) -> DocumentOut:
    """
    Speichert die Datei unter FILES_DIR/{user_id}/<uuid>.<ext>,
    zeigt im UI aber den bereinigten Originalnamen (filename) an.
    Optional: Kategorie setzen.
    Zusätzlich:
    - OCR-/Text-Content wird in documents.ocr_text gespeichert.
    - Wenn keine Kategorie gewählt wurde, wird anhand des OCR-Texts versucht,
      automatisch eine passende Kategorie zuzuweisen.
    """
    # 1) User-Verzeichnis sicherstellen
    user_dir = os.path.join(FILES_DIR, str(user_id))
    ensure_dir(user_dir)

    # 2) Anzeigename für UI/DB
    display_name = _sanitize_display_name(original_name)

    # 3) Zielpfad (UUID + Original-Ext)
    _, target_path = _unique_target_path(user_dir, display_name)

    # 4) Datei speichern + Hash berechnen
    size_bytes = save_stream_to_file(file_obj, target_path)
    with open(target_path, "rb") as fh:
        sha256_hex = sha256_of_stream(fh)

    # 5) DB anlegen (+ erste Version)
    doc = create_document_with_version(
        db=db,
        user_id=user_id,
        filename=display_name,
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,
        mime_type=None,
    )

    # 6) OCR- / Text-Extraction (best effort, Fehler brechen Upload nicht ab)
    ocr_text: Optional[str] = None
    try:
        lower_name = display_name.lower()
        if lower_name.endswith(".pdf"):
            ocr_text = extract_text_from_pdf(target_path)
        elif lower_name.endswith((".jpg", ".jpeg", ".png")):
            ocr_text = extract_text_from_image(target_path)
        elif lower_name.endswith((".docx", ".doc")):
            # Kein OCR, aber strukturierter Text-Read
            ocr_text = extract_text_from_docx(target_path)
    except Exception:
        ocr_text = None

    doc.ocr_text = ocr_text

    # 7) Kategorie setzen:
    #    - Wenn User Kategorie gewählt hat: diese nehmen
    #    - Sonst versuchen, anhand OCR-Text automatisch eine Kategorie zu finden
    if category_id is not None:
        doc.category_id = category_id
    else:
        if doc.ocr_text:
            auto_cat_id = guess_category_for_text(db, user_id, doc.ocr_text)
            if auto_cat_id is not None:
                doc.category_id = auto_cat_id

    # 8) Änderungen speichern
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256=(doc.checksum_sha256 or ""),
        created_at=getattr(doc, "created_at", None),
        category=(doc.category.name if getattr(doc, "category", None) else None),
    )


# ------------------------------------------------------------
# Detail / Download
# ------------------------------------------------------------
def get_document_detail(db: Session, user_id: int, doc_id: int) -> dict:
    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "name": doc.filename,
        "size": doc.size_bytes,
        "sha256": doc.checksum_sha256 or "",
        "mime": doc.mime_type or "",
        "created_at": getattr(doc, "created_at", None),
        "storage_path": doc.storage_path,
        "ext": (doc.filename.rsplit(".", 1)[-1].upper()) if "." in doc.filename else "FILE",
        "category_id": getattr(doc, "category_id", None),
        "category_name": getattr(doc.category, "name", None)
        if getattr(doc, "category", None)
        else None,
    }


def download_response(db: Session, user_id: int, doc_id: int) -> FileResponse:
    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        path=doc.storage_path,
        filename=doc.filename,
        media_type=doc.mime_type or "application/octet-stream",
    )


# ------------------------------------------------------------
# Rename (Dateisystem + DB)
# ------------------------------------------------------------
def rename_document_service(db: Session, user_id: int, doc_id: int, new_name: str) -> None:
    new_display_name = _sanitize_display_name(new_name)
    if not new_display_name:
        raise HTTPException(status_code=400, detail="Invalid file name")

    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    old_path = doc.storage_path
    if not old_path or not os.path.exists(old_path):
        raise HTTPException(status_code=409, detail="Stored file missing on disk")

    old_ext = os.path.splitext(doc.filename)[1]
    base_new = new_display_name if os.path.splitext(new_display_name)[1] else f"{new_display_name}{old_ext}"

    user_dir = os.path.join(FILES_DIR, str(user_id))
    ensure_dir(user_dir)
    _, new_path = _unique_target_path(user_dir, base_new)

    os.replace(old_path, new_path)

    ok = update_document_name_and_path(
        db=db,
        user_id=user_id,
        doc_id=doc_id,
        new_filename=new_display_name,
        new_storage_path=new_path,
    )
    if not ok:
        try:
            os.replace(new_path, old_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to update database")


# ------------------------------------------------------------
# Delete (Soft)
# ------------------------------------------------------------
def remove_document(db: Session, user_id: int, doc_id: int) -> bool:
    return soft_delete_document(db, doc_id, user_id)


# ------------------------------------------------------------
# Legacy-Wrapper (rückwärtskompatibel)
# ------------------------------------------------------------
def get_owned_or_404(db: Session, user_id: int, doc_id: int):
    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        raise ValueError("NOT_FOUND_OR_FORBIDDEN")
    return doc


def delete_owned_document(db: Session, user_id: int, doc_id: int) -> bool:
    _ = get_owned_or_404(db, user_id, doc_id)
    return soft_delete_document(db, doc_id, user_id)
