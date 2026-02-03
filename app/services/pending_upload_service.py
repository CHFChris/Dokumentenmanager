from __future__ import annotations

import inspect
import os
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.config import settings
from app.models.pending_upload import PendingUpload

try:
    from app.utils.crypto_utils import encrypt_bytes, decrypt_bytes, compute_integrity_tag
except Exception:  # pragma: no cover
    def encrypt_bytes(b: bytes) -> bytes:  # type: ignore
        return b

    def decrypt_bytes(b: bytes) -> bytes:  # type: ignore
        return b

    def compute_integrity_tag(b: bytes) -> str:  # type: ignore
        import hashlib
        return hashlib.sha256(b).hexdigest()


@dataclass(frozen=True)
class PendingMeta:
    token: str
    purpose: str
    context_doc_id: Optional[int]
    original_filename: Optional[str]
    mime_type: Optional[str]
    size_bytes: int
    checksum_sha256: Optional[str]


def _files_dir() -> Path:
    base = (
        getattr(settings, "FILES_DIR", None)
        or getattr(settings, "MEDIA_DIR", None)
        or getattr(settings, "STORAGE_DIR", None)
        or "./data/files"
    )
    return Path(base).resolve()


def _pending_dir(user_id: int) -> Path:
    p = _files_dir() / "_pending" / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def create_pending_upload(
    db: Session,
    *,
    user_id: int,
    purpose: str,
    raw_bytes: bytes,
    original_filename: Optional[str],
    mime_type: Optional[str],
    context_doc_id: Optional[int] = None,
) -> PendingUpload:
    token = uuid.uuid4().hex
    checksum = compute_integrity_tag(raw_bytes)
    size_bytes = len(raw_bytes)

    storage_path = _pending_dir(user_id) / f"{token}.bin"
    storage_path.write_bytes(encrypt_bytes(raw_bytes))

    pu = PendingUpload(
        owner_user_id=user_id,
        token=token,
        purpose=purpose,
        context_doc_id=context_doc_id,
        original_filename=original_filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum,
        storage_path=str(storage_path),
    )
    db.add(pu)
    db.commit()
    db.refresh(pu)
    return pu


def get_pending_upload_for_user(
    db: Session,
    *,
    user_id: int,
    token: str,
    purpose: Optional[str] = None,
) -> Optional[PendingUpload]:
    stmt = select(PendingUpload).where(
        PendingUpload.owner_user_id == user_id,
        PendingUpload.token == token,
    )
    if purpose:
        # BUGFIX: in deinem Code stand "kind" - du verwendest aber "purpose"
        stmt = stmt.where(PendingUpload.purpose == purpose)
    return db.execute(stmt).scalar_one_or_none()


def pending_meta(pu: PendingUpload) -> PendingMeta:
    return PendingMeta(
        token=pu.token,
        purpose=pu.purpose,
        context_doc_id=pu.context_doc_id,
        original_filename=pu.original_filename,
        mime_type=pu.mime_type,
        size_bytes=int(pu.size_bytes or 0),
        checksum_sha256=pu.checksum_sha256,
    )


def read_pending_bytes(pu: PendingUpload) -> bytes:
    raw = Path(pu.storage_path).read_bytes()
    return decrypt_bytes(raw)


def delete_pending_upload(db: Session, *, pu: PendingUpload) -> None:
    try:
        os.remove(pu.storage_path)
    except Exception:
        pass
    db.delete(pu)
    db.commit()


def pending_as_uploadfile(pu: PendingUpload) -> StarletteUploadFile:
    data = read_pending_bytes(pu)
    return StarletteUploadFile(
        filename=pu.original_filename or "upload.bin",
        file=BytesIO(data),
        headers=None,
    )


def _call_upload_document(
    db: Session,
    *,
    user_id: int,
    pu: PendingUpload,
    allow_duplicate: bool,
):
    from app.services.document_service import upload_document

    raw = read_pending_bytes(pu)
    bio = BytesIO(raw)

    original_name = (pu.original_filename or "upload.bin").strip() or "upload.bin"
    content_type = (pu.mime_type or "application/octet-stream").split(";")[0].strip()

    # Primär-Signatur (dein Fehler zeigt: original_name + file_obj sind Pflicht)
    try:
        return upload_document(
            db=db,
            user_id=user_id,
            file_obj=bio,
            original_name=original_name,
            content_type=content_type,
            allow_duplicate=allow_duplicate,
        )
    except TypeError:
        # Falls dein upload_document statt user_id owner_user_id nutzt
        return upload_document(
            db=db,
            owner_user_id=user_id,
            file_obj=bio,
            original_name=original_name,
            content_type=content_type,
            allow_duplicate=allow_duplicate,
        )


def _call_remove_document(db: Session, *, user_id: int, document_id: int):
    from app.services.document_service import remove_document

    sig = inspect.signature(remove_document)
    params = sig.parameters

    # Ziel: remove_document so aufrufen, wie es deine Version erwartet
    kwargs = {}

    # db
    if "db" in params:
        kwargs["db"] = db

    # Dokument-ID Parametername finden
    doc_param = None
    for name in ("document_id", "doc_id", "id"):
        if name in params:
            doc_param = name
            break

    # Owner/User Parametername finden (nicht doc_param)
    user_param = None
    for name in ("owner_user_id", "user_id", "current_user_id", "owner_id"):
        if name in params and name != doc_param:
            user_param = name
            break

    # Wenn wir passende Keyword-Namen gefunden haben: per kwargs
    if doc_param is not None:
        kwargs[doc_param] = document_id
    if user_param is not None:
        kwargs[user_param] = user_id

    # Versuch 1: Keywords
    try:
        return remove_document(**kwargs)
    except TypeError:
        pass

    # Versuch 2: positional (db, document_id, user_id)
    try:
        return remove_document(db, document_id, user_id)
    except TypeError:
        pass

    # Versuch 3: positional (document_id, user_id)
    return remove_document(document_id, user_id)


def commit_pending_to_new_document(
    db: Session,
    *,
    user_id: int,
    token: str,
    allow_duplicate: bool = True,
):
    pu = get_pending_upload_for_user(db, user_id=user_id, token=token)
    if pu is None:
        raise ValueError("PENDING_NOT_FOUND")

    doc = _call_upload_document(db, user_id=user_id, pu=pu, allow_duplicate=allow_duplicate)
    delete_pending_upload(db, pu=pu)
    return doc


def commit_pending_to_new_version(
    db: Session,
    *,
    user_id: int,
    token: str,
    note: str = "",
) -> int:
    """
    Erstellt eine neue Version für context_doc_id.
    Erwartet:
      - app.models.document.Document
      - app.models.document_version.DocumentVersion mit Feldern:
        document_id, version_number, storage_path, size_bytes, checksum_sha256, mime_type, note
    Aktualisiert Document.storage_path/size_bytes/checksum_sha256/mime_type auf die neue Version.
    """
    from app.models.document import Document
    from app.models.document_version import DocumentVersion
    from app.utils.files import ensure_dir

    pu = get_pending_upload_for_user(db, user_id=user_id, token=token, purpose="version_upload")
    if pu is None:
        raise ValueError("PENDING_NOT_FOUND")
    if not pu.context_doc_id:
        raise ValueError("PENDING_MISSING_CONTEXT")

    doc = db.execute(
        select(Document)
        .where(Document.id == int(pu.context_doc_id))
        .where(Document.owner_user_id == user_id)
        .where(Document.is_deleted.is_(False))
    ).scalar_one_or_none()
    if doc is None:
        delete_pending_upload(db, pu=pu)
        raise ValueError("DOC_NOT_FOUND")

    current_max = (
        db.execute(
            select(DocumentVersion.version_number)
            .where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        ).scalar_one_or_none()
        or 0
    )
    new_v = int(current_max) + 1

    raw = read_pending_bytes(pu)

    ext = ""
    if pu.original_filename:
        _, ext = os.path.splitext(pu.original_filename)
        ext = ext.lower()

    user_dir = _files_dir() / str(user_id)
    ensure_dir(str(user_dir))

    stored = uuid.uuid4().hex
    target_path = user_dir / f"{doc.id}.v{new_v}.{stored}{ext}"
    target_path.write_bytes(encrypt_bytes(raw))

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=new_v,
        storage_path=str(target_path),
        size_bytes=int(pu.size_bytes or len(raw)),
        checksum_sha256=pu.checksum_sha256,
        mime_type=pu.mime_type,
        note=(note or "Version Upload"),
    )
    db.add(ver)

    doc.storage_path = str(target_path)
    doc.size_bytes = int(pu.size_bytes or len(raw))
    doc.checksum_sha256 = pu.checksum_sha256
    doc.mime_type = pu.mime_type

    db.add(doc)
    db.commit()

    delete_pending_upload(db, pu=pu)
    return new_v


def replace_old_document_with_pending(
    db: Session,
    *,
    user_id: int,
    token: str,
    existing_document_id: int,
):
    pu = get_pending_upload_for_user(db, user_id=user_id, token=token)
    if pu is None:
        raise ValueError("PENDING_NOT_FOUND")

    _call_remove_document(db, user_id=user_id, document_id=existing_document_id)

    doc = _call_upload_document(db, user_id=user_id, pu=pu, allow_duplicate=True)
    delete_pending_upload(db, pu=pu)
    return doc
