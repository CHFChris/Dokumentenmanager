# app/api/routes/upload.py
from typing import Final, Optional

import os
import hashlib
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Form
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.api.deps import get_current_user, get_current_user_web, CurrentUser
from app.core.config import settings
from app.db.database import get_db
from app.schemas.document import DocumentOut
from app.utils.files import ensure_dir
from app.utils.crypto_utils import encrypt_bytes
from app.repositories.document_repo import create_document_with_version
from app.services.document_service import run_ocr_and_auto_category  # wichtig

router = APIRouter(prefix="", tags=["upload"])

# Konfig
MAX_UPLOAD_MB: Final[int] = int(getattr(settings, "MAX_UPLOAD_MB", 50))
ALLOWED_MIME: Final[set[str]] = (
    set(getattr(settings, "ALLOWED_MIME", "").split(","))  # aus env/Config
    if getattr(settings, "ALLOWED_MIME", "")
    else set()
)
FILES_DIR: Final[str] = getattr(settings, "FILES_DIR", "./data/files")


def _parse_category_id(raw: Optional[str]) -> Optional[int]:
    """
    HTML-Form schickt bei 'keine Kategorie' meist ''.
    Wandelt:
      '' / None -> None
      '5'       -> 5
      sonstiger Mist -> None
    """
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
        filename=original_name,          # sichtbarer Titel in der UI
        storage_path=target_path,        # verschlüsselter Inhalt unter stored_name
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,
        mime_type=content_type or None,
        note="Initial upload",
    )

    # neue Felder direkt am Objekt setzen, falls Modell sie kennt
    if hasattr(doc, "original_filename"):
        doc.original_filename = original_name
    if hasattr(doc, "stored_name"):
        doc.stored_name = stored_name

    # Kategorie, falls vom User gewählt
    if category_id is not None and hasattr(doc, "category_id"):
        doc.category_id = category_id

    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 8) OCR + Auto-Kategorie (best effort, Fehler werden geloggt aber nicht geworfen)
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
    category_id: Optional[str] = Form(None),  # kommt als String aus Formular/Client
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    cat_id_int = _parse_category_id(category_id)
    doc = await _handle_upload_common(db, user, file, category_id=cat_id_int)

    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256=(doc.checksum_sha256 or ""),
    )


@router.post("/upload-web")
async def upload_web(
    file: UploadFile = File(...),
    category_id: Optional[str] = Form(None),  # kommt als String aus dem HTML-Form
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    cat_id_int = _parse_category_id(category_id)
    await _handle_upload_common(db, user, file, category_id=cat_id_int)

    # Nach dem Upload auf der Upload-Seite bleiben
    return RedirectResponse(url="/upload", status_code=303)
