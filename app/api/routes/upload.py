# app/api/routes/upload.py
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Final
from uuid import uuid4
import os
import hashlib

from app.api.deps import get_current_user, get_current_user_web, CurrentUser
from app.db.database import get_db
from app.schemas.document import DocumentOut
from app.core.config import settings
from app.utils.files import ensure_dir
from app.repositories.document_repo import create_document_with_version
from app.utils.crypto_utils import encrypt_bytes

router = APIRouter(prefix="", tags=["upload"])

# Konfig
MAX_UPLOAD_MB: Final[int] = int(getattr(settings, "MAX_UPLOAD_MB", 50))
ALLOWED_MIME: Final[set[str]] = (
    set(getattr(settings, "ALLOWED_MIME", "").split(","))
    if getattr(settings, "ALLOWED_MIME", "")
    else set()
)
FILES_DIR: Final[str] = getattr(settings, "FILES_DIR", "./data/files")


async def _handle_upload_common(
    db: Session,
    user: CurrentUser,
    file: UploadFile,
):
    # 1) Basis-Validierungen
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is missing")

    content_type = (file.content_type or "").lower()

    # MIME-Whitelist (optional)
    if ALLOWED_MIME and content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=(
                f"unsupported media type '{content_type}' "
                f"(allowed: {', '.join(sorted(ALLOWED_MIME))})"
            ),
        )

    # 2) Datei in den Speicher lesen
    raw_bytes = await file.read()

    # Größenlimit prüfen
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    size_bytes = len(raw_bytes)
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file too large (>{MAX_UPLOAD_MB} MB)",
        )

    # 3) SHA256 berechnen (nur intern)
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()

    # 4) stored_name generieren (zufälliger interner Name, nichts vom Original ableitbar)
    stored_name = uuid4().hex  # 32 Hex-Zeichen

    # 5) verschlüsseln
    encrypted_bytes = encrypt_bytes(raw_bytes)

    # 6) Zielpfad: user-id + stored_name, kein Klartextname
    user_dir = os.path.join(FILES_DIR, str(user.id))
    ensure_dir(user_dir)
    target_path = os.path.join(user_dir, stored_name)

    with open(target_path, "wb") as out:
        out.write(encrypted_bytes)

    original_name = os.path.basename(file.filename)

    # 7) DB-Eintrag (Document + DocumentVersion)
    doc = create_document_with_version(
        db=db,
        user_id=user.id,
        filename=original_name,          # altes Feld
        storage_path=target_path,        # verschlüsselter Inhalt unter stored_name
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,
        mime_type=content_type or None,
        note="Initial upload",
    )

    # neue Felder direkt am Objekt setzen, falls Repo sie noch nicht kennt
    if hasattr(doc, "original_filename"):
        doc.original_filename = original_name
    if hasattr(doc, "stored_name"):
        doc.stored_name = stored_name

    db.add(doc)
    db.commit()
    db.refresh(doc)

    return doc


@router.post("/upload", response_model=DocumentOut, status_code=200)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc = await _handle_upload_common(db, user, file)

    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256=(doc.checksum_sha256 or ""),
    )


@router.post("/upload-web")
async def upload_web(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    doc = await _handle_upload_common(db, user, file)
    return RedirectResponse(url=f"/documents/{doc.id}", status_code=303)
