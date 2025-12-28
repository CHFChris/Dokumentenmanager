# app/api/routes/upload.py
from __future__ import annotations

from typing import Final, List, Optional

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
from app.services.document_service import run_ocr_and_auto_category
from app.services.document_category_service import set_document_categories

# IMMER sichtbar: zeigt dir beim Serverstart exakt, welche Datei geladen wurde
print("LOADED upload.py FROM:", __file__)

router = APIRouter(prefix="", tags=["upload"])

# Konfig
MAX_UPLOAD_MB: Final[int] = int(getattr(settings, "MAX_UPLOAD_MB", 50))
ALLOWED_MIME: Final[set[str]] = (
    set(getattr(settings, "ALLOWED_MIME", "").split(","))
    if getattr(settings, "ALLOWED_MIME", "")
    else set()
)
FILES_DIR: Final[str] = getattr(settings, "FILES_DIR", "./data/files")

# Debug: immer an (damit du es IMMER siehst)
UPLOAD_DEBUG: Final[bool] = True


def _d(msg: str) -> None:
    # IMMER drucken
    print(msg)


def _normalize_category_ids(raw: Optional[List[int]]) -> List[int]:
    """
    FastAPI liefert bei Checkboxen/Form-Listen bereits List[int].
    Diese Funktion:
    - entfernt ungültige Werte
    - entfernt Duplikate
    - behält Reihenfolge
    """
    if not raw:
        return []
    out: List[int] = []
    for x in raw:
        try:
            xi = int(x)
        except Exception:
            continue
        if xi > 0 and xi not in out:
            out.append(xi)
    return out


def _cat_ids_from_doc(doc) -> List[int]:
    cats = getattr(doc, "categories", None) or []
    ids: List[int] = []
    for c in cats:
        cid = getattr(c, "id", None)
        if isinstance(cid, int):
            ids.append(cid)
    return ids


async def _handle_upload_common(
    db: Session,
    user: CurrentUser,
    file: UploadFile,
    category_ids: Optional[List[int]] = None,
):
    _d(f"[UPLOAD][DEBUG] ENTER _handle_upload_common user_id={getattr(user, 'id', None)}")
    _d(f"[UPLOAD][DEBUG] raw category_ids param = {category_ids!r} type={type(category_ids)!r}")

    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is missing")

    content_type = (file.content_type or "").lower()
    _d(f"[UPLOAD][DEBUG] filename={file.filename!r} content_type={content_type!r}")

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
    _d(f"[UPLOAD][DEBUG] read bytes={len(raw_bytes)}")

    # Größenlimit
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    size_bytes = len(raw_bytes)
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file too large (>{MAX_UPLOAD_MB} MB)",
        )

    # HMAC statt SHA256 (Integrität)
    sha256_hex = compute_integrity_tag(raw_bytes)

    # interner Name
    stored_name = uuid4().hex

    # verschlüsseln
    encrypted_bytes = encrypt_bytes(raw_bytes)

    # Zielpfad
    user_dir = os.path.join(FILES_DIR, str(user.id))
    ensure_dir(user_dir)
    target_path = os.path.join(user_dir, stored_name)

    with open(target_path, "wb") as out_f:
        out_f.write(encrypted_bytes)

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

    db.add(doc)
    db.commit()
    db.refresh(doc)

    _d(f"[UPLOAD][DEBUG] created doc.id={getattr(doc, 'id', None)}")

    # Many-to-Many: alle angehakten Kategorien setzen
    ids = _normalize_category_ids(category_ids)
    _d(f"[UPLOAD][DEBUG] normalized category_ids = {ids}")

    if ids:
        set_document_categories(db, doc_id=doc.id, user_id=user.id, category_ids=ids)
        db.refresh(doc)
        _d(f"[UPLOAD][DEBUG] after manual set categories on doc = {_cat_ids_from_doc(doc)}")
    else:
        _d("[UPLOAD][DEBUG] no manual categories selected (ids empty)")

    # OCR + Auto-Kategorien
    try:
        _d(f"[UPLOAD][DEBUG] before OCR categories on doc = {_cat_ids_from_doc(doc)}")
        _d(f"[UPLOAD][DEBUG] calling run_ocr_and_auto_category doc_id={doc.id}")
        run_ocr_and_auto_category(
            db=db,
            user_id=user.id,
            doc=doc,
        )
        db.refresh(doc)
        _d(f"[UPLOAD][DEBUG] after OCR categories on doc = {_cat_ids_from_doc(doc)}")
    except Exception as e:
        _d(f"[UPLOAD][DEBUG] OCR crashed: {e!r}")

    _d("[UPLOAD][DEBUG] EXIT _handle_upload_common")
    return doc


@router.post("/upload", response_model=DocumentOut, status_code=200)
async def upload_file(
    file: UploadFile = File(...),
    category_ids: List[int] = Form(default=[]),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _d("[UPLOAD][DEBUG] HIT /upload")
    _d(f"[UPLOAD][DEBUG] /upload received category_ids={category_ids!r} type={type(category_ids)!r}")

    doc = await _handle_upload_common(db, user, file, category_ids=category_ids)

    categories = getattr(doc, "categories", None) or []
    _d(f"[UPLOAD][DEBUG] /upload response doc_id={doc.id} categories={_cat_ids_from_doc(doc)}")

    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256="",
        created_at=getattr(doc, "created_at", None),
        category=None,
        category_ids=[c.id for c in categories if isinstance(getattr(c, "id", None), int)],
        category_names=[c.name for c in categories if getattr(c, "name", None)],
    )


@router.post("/upload-web")
async def upload_web(
    file: UploadFile = File(...),
    category_ids: List[int] = Form(default=[]),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    _d("[UPLOAD][DEBUG] HIT /upload-web")
    _d(f"[UPLOAD][DEBUG] /upload-web received category_ids={category_ids!r} type={type(category_ids)!r}")

    await _handle_upload_common(db, user, file, category_ids=category_ids)

    _d("[UPLOAD][DEBUG] /upload-web redirecting to /upload")
    return RedirectResponse(url="/upload", status_code=303)
