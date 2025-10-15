# app/services/document_service.py
from __future__ import annotations

import os
import uuid
from typing import BinaryIO, Optional

from fastapi import HTTPException
from starlette.responses import FileResponse
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
    get_document_for_user,          # neue, einheitliche Getter-API
    update_document_name_and_path,  # atomare DB-Aktualisierung
    # Legacy-Kompatibilität (nur für Wrapper unten verwendet):
    get_document_owned as _get_document_owned_legacy,
)

# ------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------
FILES_DIR = getattr(settings, "FILES_DIR", "./data/files")


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
    # Kollision extrem unwahrscheinlich, aber sicher ist sicher:
    while os.path.exists(target_path):
        disk_name = _uuid_disk_name_with_ext(original_name_for_ext)
        target_path = os.path.join(base_dir, disk_name)
    return disk_name, target_path


# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------
def dashboard_stats(db: Session, user_id: int) -> dict:
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


# ------------------------------------------------------------
# Listing / Suche
# ------------------------------------------------------------
def list_documents(
    db: Session,
    user_id: int,
    q: Optional[str],
    limit: int,
    offset: int,
) -> DocumentListOut:
    """
    Listet Dokumente des Users (nicht gelöschte) mit optionalem Suchstring (case-insensitive).
    """
    rows, total = list_documents_for_user(db, user_id, q, limit, offset)
    items = [
        DocumentOut(
            id=r.id,
            name=r.filename,                  # Schema erwartet "name"
            size=r.size_bytes,                # Schema erwartet "size"
            sha256=(r.checksum_sha256 or ""), # Schema erwartet "sha256"
        )
        for r in rows
    ]
    return DocumentListOut(items=items, total=total)


# ------------------------------------------------------------
# Upload
# ------------------------------------------------------------
def upload_document(
    db: Session,
    user_id: int,
    original_name: str,
    file_obj: BinaryIO,
) -> DocumentOut:
    """
    Speichert die Datei unter FILES_DIR/{user_id}/<uuid>.<ext>,
    zeigt im UI aber den bereinigten Originalnamen (filename) an.
    """
    # 1) User-Verzeichnis sicherstellen
    user_dir = os.path.join(FILES_DIR, str(user_id))
    ensure_dir(user_dir)

    # 2) Anzeigename für UI/DB
    display_name = _sanitize_display_name(original_name)

    # 3) Zielpfad (UUID + Original-Ext)
    disk_name, target_path = _unique_target_path(user_dir, display_name)

    # 4) Datei speichern + Hash berechnen
    size_bytes = save_stream_to_file(file_obj, target_path)
    with open(target_path, "rb") as fh:
        sha256_hex = sha256_of_stream(fh)

    # 5) DB anlegen (+ erste Version)
    doc = create_document_with_version(
        db=db,
        user_id=user_id,
        filename=display_name,     # schöner Anzeigename
        storage_path=target_path,  # echter Pfad auf Disk
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


# ------------------------------------------------------------
# Detail / Download
# ------------------------------------------------------------
def get_document_detail(db: Session, user_id: int, doc_id: int) -> dict:
    """
    Liefert Detailinformationen (für API/Template).
    """
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
    }


def download_response(db: Session, user_id: int, doc_id: int) -> FileResponse:
    """
    Liefert eine FileResponse mit sicherem Content-Type-Fallback.
    """
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
    """
    Bennennt ein Dokument sicher um:
    - validiert neuen Namen
    - behält vorhandene Dateiendung, falls keine angegeben
    - verschiebt Datei atomar in FILES_DIR/{user_id}/
    - aktualisiert DB (filename + storage_path) atomar
    """
    # validierter Anzeigename (für DB/UI)
    new_display_name = _sanitize_display_name(new_name)
    if not new_display_name:
        raise HTTPException(status_code=400, detail="Invalid file name")

    # Dokument holen + Plausibilitäten
    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    old_path = doc.storage_path
    if not old_path or not os.path.exists(old_path):
        # Inkonsistenz bewusst signalisieren
        raise HTTPException(status_code=409, detail="Stored file missing on disk")

    # Dateiendung beibehalten, wenn neue keinen Punkt hat
    old_ext = os.path.splitext(doc.filename)[1]
    base_new = new_display_name if os.path.splitext(new_display_name)[1] else f"{new_display_name}{old_ext}"

    # Zielpfad im User-Ordner (UUID + ext, damit Disk eindeutig bleibt)
    user_dir = os.path.join(FILES_DIR, str(user_id))
    ensure_dir(user_dir)
    new_disk_name, new_path = _unique_target_path(user_dir, base_new)

    # Physisch verschieben (atomar auf derselben Partition)
    os.replace(old_path, new_path)

    # DB aktualisieren – filename (Anzeige) und storage_path (Disk)
    ok = update_document_name_and_path(
        db=db,
        user_id=user_id,
        doc_id=doc_id,
        new_filename=new_display_name,  # Anzeige-/UI-Name!
        new_storage_path=new_path,
    )
    if not ok:
        # Best effort Rollback der Datei
        try:
            os.replace(new_path, old_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to update database")


# ------------------------------------------------------------
# Delete (Soft)
# ------------------------------------------------------------
def remove_document(db: Session, user_id: int, doc_id: int) -> bool:
    """
    Soft-Delete in der DB (Datei bleibt physisch erhalten).
    """
    return soft_delete_document(db, doc_id, user_id)


# ------------------------------------------------------------
# Legacy-Wrapper (rückwärtskompatibel)
# ------------------------------------------------------------
def get_owned_or_404(db: Session, user_id: int, doc_id: int):
    """
    Legacy-Verhalten: wirft ValueError, wenn nicht gefunden.
    Router mappt das auf 404/403.
    """
    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        raise ValueError("NOT_FOUND_OR_FORBIDDEN")
    return doc


def delete_owned_document(db: Session, user_id: int, doc_id: int) -> bool:
    """
    Legacy-Verhalten: zuerst Ownership/Existenz prüfen, dann soft-deleten.
    """
    _ = get_owned_or_404(db, user_id, doc_id)
    return soft_delete_document(db, doc_id, user_id)
