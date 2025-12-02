# app/api/routes/upload.py
from typing import Final, Optional

import os
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Form
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.api.deps import get_current_user, get_current_user_web, CurrentUser
from app.core.config import settings
from app.db.database import get_db
from app.schemas.document import DocumentOut
from app.utils.files import ensure_dir
from app.utils.crypto_utils import encrypt_bytes, compute_integrity_tag
from app.repositories.document_repo import create_document_with_version
from app.services.document_service import run_ocr_and_auto_category  # wichtig

router = APIRouter(prefix="", tags=["upload"])

# Konfig
MAX_UPLOAD_MB: Final[int] = int(getattr(settings, "MAX_UPLOAD_MB", 50))
ALLOWED_MIME: Final[set[str]] = (
    set(getattr(settings, "ALLOWED_MIME", "").split(","))
    if getattr(settings, "ALLOWED_MIME", "")
    else set()
)
FILES_DIR: Final[str] = getattr(settings, "FILES_DIR", "./data/files")


def _parse_category_id(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _handle_upload_common(
    db: Session,
    user: CurrentUser,
    file: UploadFile,
    category_id: Optional[int] = None,
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is missing")

    content_type = (file.content_type or "").lower()

    if ALLOWED_MIME and content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=(
                f"unsupported media type '{content_type}' "
                f"(allowed: {', '.join(sorted(ALLOWED_MIME))})"
            ),
        )

    # Datei laden
    raw_bytes = await file.read()

    # Größenlimit
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    size_bytes = len(raw_bytes)
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file too large (>{MAX_UPLOAD_MB} MB)",
        )

    # NEU: HMAC statt SHA256
    sha256_hex = compute_integrity_tag(raw_bytes)

    # interner Name
    stored_name = uuid4().hex

    # verschlüsseln
    encrypted_bytes = encrypt_bytes(raw_bytes)

    # Zielpfad
    user_dir = os.path.join(FILES_DIR, str(user.id))
    ensure_dir(user_dir)
    target_path = os.path.join(user_dir, stored_name)

    with open(target_path, "wb") as out:
        out.write(encrypted_bytes)

    original_name = os.path.basename(file.filename)

    # Datenbank
    doc = create_document_with_version(
        db=db,
        user_id=user.id,
        filename=original_name,
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,  # jetzt HMAC
        mime_type=content_type or None,
        note="Initial upload",
    )

    if hasattr(doc, "original_filename"):
        doc.original_filename = original_name
    if hasattr(doc, "stored_name"):
        doc.stored_name = stored_name

    if category_id is not None and hasattr(doc, "category_id"):
        doc.category_id = category_id

    db.add(doc)
    db.commit()
    db.refresh(doc)

    # OCR + Auto-Kategorie
    try:
        print(f"[UPLOAD] Starte run_ocr_and_auto_category für Doc {doc.id}")
        run_ocr_and_auto_category(
            db=db,
            user_id=user.id,
            doc=doc,
        )
        db.refresh(doc)
    except Exception as e:
        print(f"[UPLOAD] Fehler in run_ocr_and_auto_category: {e!r}")

    return doc


@router.post("/upload", response_model=DocumentOut, status_code=200)
async def upload_file(
    file: UploadFile = File(...),
    category_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    cat_id_int = _parse_category_id(category_id)
    doc = await _handle_upload_common(db, user, file, category_id=cat_id_int)

    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256="",
    )


@router.post("/upload-web")
async def upload_web(
    file: UploadFile = File(...),
    category_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    cat_id_int = _parse_category_id(category_id)
    await _handle_upload_common(db, user, file, category_id=cat_id_int)

    return RedirectResponse(url="/upload", status_code=303)
