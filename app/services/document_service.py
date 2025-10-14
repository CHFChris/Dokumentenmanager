# app/services/document_service.py
from __future__ import annotations

import os
import uuid
from typing import BinaryIO, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.document import DocumentListOut, DocumentOut
from app.utils.files import ensure_dir, save_stream_to_file, sha256_of_stream

from app.repositories.document_repo import (
    # Dashboard
    count_documents_for_user,
    storage_used_for_user,
    recent_uploads_count_week,
    recent_uploads_for_user,
    # Documents
    list_documents_for_user,
    create_document_with_version,
    soft_delete_document,
)

# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------
def dashboard_stats(db: Session, user_id: int) -> dict:
    """Aggregierte Kennzahlen fürs Dashboard."""
    total = count_documents_for_user(db, user_id)
    storage = storage_used_for_user(db, user_id)
    recent_week = recent_uploads_count_week(db, user_id)
    recent_items = recent_uploads_for_user(db, user_id, limit=5)
    return {
        "total": total,
        "storage_bytes": storage,
        "recent_week": recent_week,
        "recent_items": recent_items,
    }


# ---------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------
FILES_DIR = getattr(settings, "FILES_DIR", "./data/files")


def list_documents(
    db: Session,
    user_id: int,
    q: Optional[str],
    limit: int,
    offset: int,
) -> DocumentListOut:
    """Liste der Dokumente eines Users mit optionaler Suche & Paging."""
    rows, total = list_documents_for_user(db, user_id, q, limit, offset)
    items = [
        DocumentOut(
            id=r.id,
            name=r.filename,
            size=r.size_bytes,
            sha256=(r.checksum_sha256 or ""),
        )
        for r in rows
    ]
    return DocumentListOut(items=items, total=total)


def _unique_disk_name(base_name: str) -> str:
    """
    Vermeidet Kollisionen auf dem Dateisystem:
    existiert die Datei bereits, wird ' (UUID4)' vor die Erweiterung gesetzt.
    """
    name, ext = os.path.splitext(base_name)
    candidate = base_name
    while os.path.exists(os.path.join(FILES_DIR, candidate)):
        candidate = f"{name} ({uuid.uuid4().hex[:8]}){ext}"
    return candidate


def upload_document(
    db: Session,
    user_id: int,
    original_name: str,
    file_obj: BinaryIO,
) -> DocumentOut:
    """
    Speichert die Datei im FILES_DIR, berechnet SHA256 und legt den DB-Datensatz
    inkl. Version an.
    """
    ensure_dir(FILES_DIR)

    base_name = os.path.basename(original_name)
    disk_name = _unique_disk_name(base_name)
    target_path = os.path.join(FILES_DIR, disk_name)

    # Datei speichern
    size_bytes = save_stream_to_file(file_obj, target_path)

    # Hash berechnen (Datei erneut öffnen)
    with open(target_path, "rb") as fh:
        sha256_hex = sha256_of_stream(fh)

    # DB anlegen (+ erste Version)
    doc = create_document_with_version(
        db=db,
        user_id=user_id,
        filename=disk_name,           # gespeicherter Name (ggf. uniquified)
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,
        mime_type=None,
    )

    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256=(doc.checksum_sha256 or ""),
    )


def remove_document(db: Session, user_id: int, doc_id: int) -> bool:
    """Soft-Delete auf Datenbankebene (Datei bleibt physisch erhalten)."""
    return soft_delete_document(db, doc_id, user_id)
