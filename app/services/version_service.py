# app/services/version_service.py
import os, shutil, uuid
from typing import BinaryIO
from sqlalchemy.orm import Session
from app.repositories.document_repo import (
    get_document_owned, list_versions_for_document, add_version, get_version_owned
)
from app.utils.files import ensure_dir, save_stream_to_file, sha256_of_stream
from app.core.config import settings

BASE_FILES_DIR = getattr(settings, "FILES_DIR", "./data/files")

def _user_dir(user_id: int) -> str:
    return os.path.join(BASE_FILES_DIR, str(user_id))

def list_versions(db: Session, user_id: int, doc_id: int):
    doc = get_document_owned(db, doc_id, user_id)
    if not doc:
        raise ValueError("NOT_FOUND_OR_FORBIDDEN")
    vers = list_versions_for_document(db, doc_id, user_id)
    return doc, vers

def upload_new_version(db: Session, user_id: int, doc_id: int, original_name: str, file_obj: BinaryIO, note: str | None):
    doc = get_document_owned(db, doc_id, user_id)
    if not doc:
        raise ValueError("NOT_FOUND_OR_FORBIDDEN")

    ensure_dir(_user_dir(user_id))
    _, ext = os.path.splitext(original_name or doc.filename)
    disk_name = f"{uuid.uuid4().hex}{ext.lower()}"
    target_path = os.path.join(_user_dir(user_id), disk_name)

    size_bytes = save_stream_to_file(file_obj, target_path)
    with open(target_path, "rb") as fh:
        sha256_hex = sha256_of_stream(fh)

    ver = add_version(
        db=db,
        doc=doc,
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,
        mime_type=doc.mime_type,  # oder UploadFile.content_type, wenn vorhanden
        note=note or "Content updated",
    )
    return ver

def rename_document_creates_version(db: Session, user_id: int, doc_id: int, new_title: str):
    """
    „Nur Metadaten geändert“ => neue Version erstellen, die auf denselben Inhalt zeigt.
    So bleibt der Verlauf konsistent und wir können die Änderung historisieren.
    """
    doc = get_document_owned(db, doc_id, user_id)
    if not doc:
        raise ValueError("NOT_FOUND_OR_FORBIDDEN")

    # Speichere *Inhalt unverändert*, aber aktualisiere Document.filename (sichtbarer Titel)
    # und lege trotzdem eine neue Version an (gleiches storage_path).
    # Für ‚add_version‘ brauchen wir size/hash des aktuellen Stands:
    size = doc.size_bytes or 0
    checksum = doc.checksum_sha256
    add_version(
        db=db,
        doc=doc,
        storage_path=doc.storage_path,
        size_bytes=size,
        checksum_sha256=checksum,
        mime_type=doc.mime_type,
        note=f"Renamed to '{new_title}'",
    )
    # Danach Document-Titel aktualisieren (nicht Teil der Versionstabelle)
    doc.filename = new_title
    db.commit()
    db.refresh(doc)
    return doc

def restore_version(db: Session, user_id: int, doc_id: int, version_id: int):
    """
    Wiederherstellen = neue Version erzeugen, deren Inhalt eine *Kopie* der gewählten Version ist.
    (Wir überschreiben nicht retrospektiv Dateien; Historie bleibt unverändert.)
    """
    doc = get_document_owned(db, doc_id, user_id)
    if not doc:
        raise ValueError("NOT_FOUND_OR_FORBIDDEN")
    ver = get_version_owned(db, doc_id, version_id, user_id)
    if not ver:
        raise ValueError("NOT_FOUND_OR_FORBIDDEN")

    ensure_dir(_user_dir(user_id))
    _, ext = os.path.splitext(doc.filename or "")
    disk_name = f"{uuid.uuid4().hex}{ext.lower() or ''}"
    target_path = os.path.join(_user_dir(user_id), disk_name)

    shutil.copy2(ver.storage_path, target_path)
    size_bytes = os.path.getsize(target_path)
    with open(target_path, "rb") as fh:
        sha256_hex = sha256_of_stream(fh)

    new_ver = add_version(
        db=db,
        doc=doc,
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,
        mime_type=ver.mime_type,
        note=f"Restored from v{ver.version_number}",
    )
    return new_ver
