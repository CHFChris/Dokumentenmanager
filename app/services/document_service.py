import os
from typing import BinaryIO
from sqlalchemy.orm import Session
from app.repositories.document_repo import (
    list_documents_for_user,
    create_document_with_version,
    soft_delete_document,
)
from app.schemas.document import DocumentListOut, DocumentOut
from app.core.config import settings
from app.utils.files import ensure_dir, save_stream_to_file, sha256_of_stream

FILES_DIR = getattr(settings, "FILES_DIR", "./data/files")

def list_documents(db: Session, user_id: int, q: str | None, limit: int, offset: int) -> DocumentListOut:
    rows, total = list_documents_for_user(db, user_id, q, limit, offset)
    items = [
        DocumentOut(
            id=r.id,
            name=r.filename,
            size=r.size_bytes,
            sha256=r.checksum_sha256,
        )
        for r in rows
    ]
    return DocumentListOut(items=items, total=total)

def upload_document(db: Session, user_id: int, original_name: str, file_obj: BinaryIO) -> DocumentOut:
    ensure_dir(FILES_DIR)

    # Zielpfad erzeugen
    base_name = os.path.basename(original_name)
    disk_name = base_name  # einfache Variante; bei Bedarf mit UUID erweitern
    target_path = os.path.join(FILES_DIR, disk_name)

    # Datei speichern + Hash berechnen
    size_bytes = save_stream_to_file(file_obj, target_path)
    sha256_hex = sha256_of_stream(open(target_path, "rb"))

    # in DB anlegen (documents + document_versions)
    doc = create_document_with_version(
        db=db,
        user_id=user_id,
        filename=base_name,
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,
        mime_type=None,  # falls du UploadFile.content_type durchreichen willst: setze es hier
    )

    return DocumentOut(id=doc.id, name=doc.filename, size=doc.size_bytes, sha256=doc.checksum_sha256)

def remove_document(db: Session, user_id: int, doc_id: int) -> bool:
    return soft_delete_document(db, doc_id, user_id)
