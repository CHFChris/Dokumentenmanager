# app/api/routes/upload.py
from __future__ import annotations

<<<<<<< HEAD
from typing import Final, Optional
=======
from typing import Final, List, Optional, Tuple
>>>>>>> backup/feature-snapshot

import os
import mimetypes
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
<<<<<<< HEAD
from app.repositories.document_repo import create_document_with_version
from app.services.document_service import run_ocr_and_auto_category  # wichtig
from app.services.document_category_service import set_document_categories  # NEU
=======
from app.repositories.document_repo import create_document_with_version, get_by_sha_or_name_size
from app.services.document_service import run_ocr_and_auto_category
from app.services.document_category_service import set_document_categories

# IMMER sichtbar: zeigt dir beim Serverstart exakt, welche Datei geladen wurde
print("LOADED upload.py FROM:", __file__)
>>>>>>> backup/feature-snapshot

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

<<<<<<< HEAD
def _parse_category_ids(raw: Optional[str]) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = (part or "").strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return list(dict.fromkeys(out))
=======

def _d(msg: str) -> None:
    # IMMER drucken
    print(msg)


class DuplicateDocumentError(Exception):
    def __init__(self, existing_id: int, by: str = "sha256"):
        self.existing_id = int(existing_id)
        self.by = (by or "sha256").strip()
        super().__init__(f"Duplicate document detected (by={self.by}, existing_id={self.existing_id})")


def find_duplicate(
    db: Session,
    user_id: int,
    sha256: Optional[str],
    name: Optional[str],
    size: Optional[int],
) -> Tuple[Optional[object], Optional[str]]:
    """
    Prüft Duplikat über:
    - checksum_sha256 (falls sha256 gesetzt)
    - filename (case-insensitive) + size_bytes (falls beides gesetzt)

    Rückgabe: (Document|None, "sha256"|"name_size"|None)
    """
    sha256 = (sha256 or "").strip()
    name = (name or "").strip()
    size_val: Optional[int]
    try:
        size_val = int(size) if size is not None else None
    except Exception:
        size_val = None

    doc = get_by_sha_or_name_size(
        db=db,
        user_id=user_id,
        sha256=sha256 or None,
        filename=name or None,
        size_bytes=size_val,
    )
    if not doc:
        return None, None

    by = "name_size"
    try:
        if sha256 and getattr(doc, "checksum_sha256", None) == sha256:
            by = "sha256"
        elif name and size_val is not None:
            fn = getattr(doc, "filename", None) or ""
            sb = getattr(doc, "size_bytes", None)
            if str(fn).lower() == name.lower() and sb == size_val:
                by = "name_size"
    except Exception:
        pass

    return doc, by


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
>>>>>>> backup/feature-snapshot


async def _handle_upload_common(
    db: Session,
    user: CurrentUser,
    file: UploadFile,
<<<<<<< HEAD
    category_ids: Optional[str] = None,
=======
    category_ids: Optional[List[int]] = None,
    allow_duplicate: bool = False,
>>>>>>> backup/feature-snapshot
):
    _d(f"[UPLOAD][DEBUG] ENTER _handle_upload_common user_id={getattr(user, 'id', None)} allow_duplicate={allow_duplicate}")
    _d(f"[UPLOAD][DEBUG] raw category_ids param = {category_ids!r} type={type(category_ids)!r}")

    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is missing")

    content_type = (file.content_type or "").split(";")[0].strip().lower()

    # Fallback: Browser liefert manchmal nur application/octet-stream
    if (not content_type) or (content_type == "application/octet-stream"):
        guessed, _ = mimetypes.guess_type(file.filename)
        if guessed:
            content_type = guessed.lower()

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

    # Duplikatserkennung (Hash oder Name+Groesse) vor dem Schreiben der Datei
    # allow_duplicate=True ueberspringt die Erkennung (Userentscheidung).
    if not allow_duplicate:
        dup_doc, dup_by = find_duplicate(
            db=db,
            user_id=user.id,
            sha256=sha256_hex,
            name=os.path.basename(file.filename),
            size=size_bytes,
        )
        if dup_doc:
            raise DuplicateDocumentError(existing_id=dup_doc.id, by=str(dup_by or "sha256"))

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

    # Datenbank (Metadaten + eindeutiger stored_name)
    doc = create_document_with_version(
        db=db,
        user_id=user.id,
        filename=original_name,
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,  # HMAC-SHA256 Integritaetstag
        mime_type=content_type or None,
        note="Initial upload",
        original_filename=original_name,
        stored_name=stored_name,
    )

    _d(f"[UPLOAD][DEBUG] created doc.id={getattr(doc, 'id', None)}")

<<<<<<< HEAD
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # NEU: Many-to-Many Kategorien manuell setzen (ohne category_id)
    ids = _parse_category_ids(category_ids)
    if ids:
        set_document_categories(db, doc_id=doc.id, user_id=user.id, category_ids=ids)
        db.refresh(doc)

    # OCR + Auto-Kategorien (Top-N) -> ergänzt später weitere Kategorien
=======
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
>>>>>>> backup/feature-snapshot
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
<<<<<<< HEAD
    category_ids: Optional[str] = Form(None),  # NEU: "1,2,3"
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc = await _handle_upload_common(db, user, file, category_ids=category_ids)
=======
    category_ids: List[int] = Form(default=[]),
    allow_duplicate: bool = Form(False),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _d("[UPLOAD][DEBUG] HIT /upload")
    _d(f"[UPLOAD][DEBUG] /upload received category_ids={category_ids!r} type={type(category_ids)!r} allow_duplicate={allow_duplicate}")

    try:
        doc = await _handle_upload_common(
            db,
            user,
            file,
            category_ids=category_ids,
            allow_duplicate=allow_duplicate,
        )
    except DuplicateDocumentError as e:
        raise HTTPException(
            status_code=409,
            detail={"message": "duplicate_detected", "existing_id": e.existing_id, "by": e.by},
        )

    categories = getattr(doc, "categories", None) or []
    _d(f"[UPLOAD][DEBUG] /upload response doc_id={doc.id} categories={_cat_ids_from_doc(doc)}")
>>>>>>> backup/feature-snapshot

    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256="",
        created_at=getattr(doc, "created_at", None),
        category=None,
<<<<<<< HEAD
        category_ids=[c.id for c in (getattr(doc, "categories", None) or []) if isinstance(getattr(c, "id", None), int)],
        category_names=[c.name for c in (getattr(doc, "categories", None) or []) if getattr(c, "name", None)],
=======
        category_ids=[c.id for c in categories if isinstance(getattr(c, "id", None), int)],
        category_names=[c.name for c in categories if getattr(c, "name", None)],
>>>>>>> backup/feature-snapshot
    )


@router.post("/upload-web")
async def upload_web(
    file: UploadFile = File(...),
<<<<<<< HEAD
    category_ids: Optional[str] = Form(None),  # NEU: "1,2,3"
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    await _handle_upload_common(db, user, file, category_ids=category_ids)
    return RedirectResponse(url="/upload", status_code=303)
=======
    category_ids: List[int] = Form(default=[]),
    allow_duplicate: bool = Form(False),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    _d("[UPLOAD][DEBUG] HIT /upload-web")
    _d(f"[UPLOAD][DEBUG] /upload-web received category_ids={category_ids!r} type={type(category_ids)!r} allow_duplicate={allow_duplicate}")

    try:
        await _handle_upload_common(
            db,
            user,
            file,
            category_ids=category_ids,
            allow_duplicate=allow_duplicate,
        )
        _d("[UPLOAD][DEBUG] /upload-web redirecting to /upload")
        return RedirectResponse(url="/upload", status_code=303)
    except DuplicateDocumentError as e:
        return RedirectResponse(
            url=f"/upload?duplicate=1&existing_id={e.existing_id}",
            status_code=303,
        )
>>>>>>> backup/feature-snapshot
