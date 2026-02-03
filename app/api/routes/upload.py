from __future__ import annotations

from typing import Final, List, Optional

import os
import mimetypes
import uuid
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, UploadFile, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_web, CurrentUser
from app.core.config import settings
from app.db.database import get_db
from app.models.document import Document
from app.repositories.document_repo import get_by_sha_or_name_size, create_document_with_version
from app.schemas.document import DocumentOut
from app.services.document_category_service import set_document_categories
from app.services.document_service import run_ocr_and_auto_category
from app.utils.crypto_utils import encrypt_bytes, compute_integrity_tag
from app.utils.files import ensure_dir

from app.services.pending_upload_service import (
    create_pending_upload,
    get_pending_upload_for_user,
    pending_meta,
    delete_pending_upload,
    read_pending_bytes,
    commit_pending_to_new_document,
    replace_old_document_with_pending,
)

# IMMER sichtbar: zeigt dir beim Serverstart exakt, welche Datei geladen wurde
print("LOADED upload.py FROM:", __file__)

router = APIRouter(prefix="", tags=["upload"])
templates = Jinja2Templates(directory="app/web/templates")

# Konfig
MAX_UPLOAD_MB: Final[int] = int(getattr(settings, "MAX_UPLOAD_MB", 50))
ALLOWED_MIME: Final[set[str]] = (
    set(getattr(settings, "ALLOWED_MIME", "").split(","))
    if getattr(settings, "ALLOWED_MIME", "")
    else set()
)
FILES_DIR: Final[str] = getattr(settings, "FILES_DIR", "./data/files")


def _normalize_category_ids(raw: Optional[List[int]]) -> List[int]:
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


def _cat_ids_from_doc(doc: Document) -> List[int]:
    cats = getattr(doc, "categories", None) or []
    ids: List[int] = []
    for c in cats:
        cid = getattr(c, "id", None)
        if isinstance(cid, int):
            ids.append(cid)
    return ids


def _cat_names_from_doc(doc: Document) -> List[str]:
    cats = getattr(doc, "categories", None) or []
    names: List[str] = []
    for c in cats:
        nm = getattr(c, "name", None)
        if nm:
            names.append(str(nm))
    return names


def _doc_to_out(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256="",
        created_at=getattr(doc, "created_at", None),
        category=None,
        category_ids=_cat_ids_from_doc(doc),
        category_names=_cat_names_from_doc(doc),
    )


def _user_dir(user_id: int) -> str:
    p = os.path.join(FILES_DIR, str(user_id))
    ensure_dir(p)
    return p


def _set_toast_cookie(resp: RedirectResponse, *, level: str, message: str) -> None:
    resp.set_cookie(
        key="toast",
        value=f"{level}:{message}",
        max_age=10,
        httponly=False,
        samesite="lax",
    )


def _validate_upload(file: UploadFile, raw_bytes: bytes) -> tuple[str, int]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is missing")

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if (not content_type) or (content_type == "application/octet-stream"):
        guessed, _ = mimetypes.guess_type(file.filename)
        if guessed:
            content_type = guessed.lower()

    if ALLOWED_MIME and content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=(
                f"unsupported media type '{content_type}' "
                f"(allowed: {', '.join(sorted(ALLOWED_MIME))})"
            ),
        )

    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    size_bytes = len(raw_bytes)
    if size_bytes <= 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if size_bytes > max_bytes:
        raise HTTPException(status_code=413, detail=f"file too large (>{MAX_UPLOAD_MB} MB)")

    return content_type, size_bytes


def _persist_new_document_from_bytes(
    db: Session,
    *,
    user_id: int,
    filename: str,
    content_type: Optional[str],
    raw_bytes: bytes,
    checksum: str,
    category_ids: Optional[List[int]] = None,
    note: str = "Initial upload",
) -> Document:
    ext = os.path.splitext(filename or "")[1].lower()
    stored_name = uuid.uuid4().hex

    user_dir = _user_dir(user_id)
    target_path = os.path.join(user_dir, f"{stored_name}{ext}")

    encrypted = encrypt_bytes(raw_bytes)
    with open(target_path, "wb") as f:
        f.write(encrypted)

    doc = create_document_with_version(
        db=db,
        user_id=user_id,
        filename=os.path.basename(filename or "upload"),
        storage_path=target_path,
        size_bytes=len(raw_bytes),
        checksum_sha256=checksum,
        mime_type=content_type,
        note=note,
        original_filename=os.path.basename(filename or "upload"),
        stored_name=stored_name,
    )

    ids = _normalize_category_ids(category_ids)
    if ids:
        set_document_categories(db=db, user_id=user_id, doc_id=doc.id, category_ids=ids)
        db.refresh(doc)

    try:
        run_ocr_and_auto_category(db=db, user_id=user_id, doc=doc)
        db.refresh(doc)
    except Exception:
        pass

    return doc


@router.get("/upload", response_class=HTMLResponse, include_in_schema=False)
def web_upload_page(
    request: Request,
    duplicate: int = Query(0),
    existing_id: Optional[int] = Query(None),
    pending: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    ctx = {
        "request": request,
        "user": user,
        "duplicate": bool(duplicate),
        "existing_id": existing_id,
        "pending_token": pending,
        "existing_doc": None,
        "pending_upload": None,
    }

    # Duplikatmodus: bestehendes Dokument + PendingUpload laden
    if duplicate and existing_id and pending:
        existing_doc = db.execute(
            select(Document)
            .where(Document.id == existing_id)
            .where(Document.owner_user_id == user.id)
            .where(Document.is_deleted.is_(False))
        ).scalar_one_or_none()

        pending_upload = get_pending_upload_for_user(db, user_id=user.id, token=pending)

        # Nur wenn beides existiert, bleiben wir im Duplikatmodus
        if existing_doc is not None and pending_upload is not None:
            ctx["existing_doc"] = existing_doc
            ctx["pending_upload"] = pending_upload
        else:
            ctx["duplicate"] = False

    return templates.TemplateResponse("upload.html", ctx)


@router.post("/upload", response_model=DocumentOut, status_code=200)
async def upload_api(
    file: UploadFile = File(...),
    category_ids: Optional[List[int]] = Form(None),
    allow_duplicate: bool = Form(False),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw_bytes = await file.read()
    content_type, size_bytes = _validate_upload(file, raw_bytes)

    checksum = compute_integrity_tag(raw_bytes)

    if not allow_duplicate:
        dup = get_by_sha_or_name_size(
            db=db,
            user_id=user.id,
            sha256=checksum,
            filename=os.path.basename(file.filename),
            size_bytes=size_bytes,
        )
        if dup:
            raise HTTPException(status_code=409, detail="Duplicate document")

    doc = _persist_new_document_from_bytes(
        db,
        user_id=user.id,
        filename=file.filename,
        content_type=content_type or None,
        raw_bytes=raw_bytes,
        checksum=checksum,
        category_ids=category_ids,
        note="Initial upload",
    )
    return _doc_to_out(doc)


@router.post("/upload-web")
async def upload_web(
    request: Request,
    file: UploadFile = File(...),
    category_ids: Optional[List[int]] = Form(None),
    allow_duplicate: bool = Form(False),
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    raw_bytes = await file.read()
    if not raw_bytes:
        return RedirectResponse(url="/upload", status_code=303)

    try:
        content_type, size_bytes = _validate_upload(file, raw_bytes)
    except HTTPException as e:
        resp = RedirectResponse(url="/upload", status_code=303)
        _set_toast_cookie(resp, level="error", message=str(e.detail))
        return resp

    checksum = compute_integrity_tag(raw_bytes)

    if not allow_duplicate:
        dup = get_by_sha_or_name_size(
            db=db,
            user_id=user.id,
            sha256=checksum,
            filename=os.path.basename(file.filename),
            size_bytes=size_bytes,
        )
        if dup:
            pu = create_pending_upload(
                db=db,
                user_id=user.id,
                raw_bytes=raw_bytes,
                original_filename=os.path.basename(file.filename),
                mime_type=content_type or None,
                purpose="document_upload",
            )
            resp = RedirectResponse(
                url=f"/upload?duplicate=1&existing_id={dup.id}&pending={pu.token}",
                status_code=303,
            )
            _set_toast_cookie(resp, level="warning", message="Duplikat erkannt")
            return resp

    _persist_new_document_from_bytes(
        db,
        user_id=user.id,
        filename=file.filename,
        content_type=content_type or None,
        raw_bytes=raw_bytes,
        checksum=checksum,
        category_ids=category_ids,
        note="Initial upload",
    )

    resp = RedirectResponse(url="/documents", status_code=303)
    _set_toast_cookie(resp, level="success", message="Upload erfolgreich")
    return resp


@router.post("/upload-web/duplicate/commit", include_in_schema=False)
def upload_duplicate_commit(
    token: str = Form(...),
    keep_old: bool = Form(True),
    existing_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    # keep_old=True  -> altes bleibt, neues wird zusätzlich gespeichert
    # keep_old=False -> altes wird gelöscht, neues übernimmt (ersetzen)
    if existing_id is not None and keep_old is False:
        doc = replace_old_document_with_pending(
            db=db,
            user_id=user.id,
            token=token,
            existing_document_id=existing_id,
        )
    else:
        doc = commit_pending_to_new_document(
            db=db,
            user_id=user.id,
            token=token,
            allow_duplicate=True,
        )

    return RedirectResponse(url=f"/documents/{doc.id}", status_code=303)


@router.post("/upload-web/duplicate/replace-old", include_in_schema=False)
def upload_duplicate_replace_old(
    token: str = Form(...),
    existing_id: int = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    return upload_duplicate_commit(
        token=token,
        keep_old=False,
        existing_id=existing_id,
        db=db,
        user=user,
    )


@router.post("/upload-web/duplicate/discard", include_in_schema=False)
def upload_duplicate_discard(
    token: str = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    pu = get_pending_upload_for_user(db, user_id=user.id, token=token)
    if pu is not None:
        delete_pending_upload(db, pu=pu)
    return RedirectResponse(url="/upload", status_code=303)


@router.get("/upload/pending/{token}/preview", include_in_schema=False)
def web_pending_preview(
    token: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    pu = get_pending_upload_for_user(db, user_id=user.id, token=token)
    if not pu:
        raise HTTPException(status_code=404, detail="Pending not found")
    return RedirectResponse(url=f"/upload/pending/{token}/download?inline=1", status_code=303)


@router.get("/upload/pending/{token}/view", include_in_schema=False)
def web_pending_view(
    token: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    pu = get_pending_upload_for_user(db, user_id=user.id, token=token)
    if not pu:
        raise HTTPException(status_code=404, detail="Pending not found")
    return RedirectResponse(url=f"/upload/pending/{token}/download?inline=1", status_code=303)


@router.get("/upload/pending/{token}/download", include_in_schema=False)
def web_pending_download(
    token: str,
    inline: int = 1,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    pu = get_pending_upload_for_user(db, user_id=user.id, token=token)
    if not pu:
        raise HTTPException(status_code=404, detail="Pending not found")

    raw = read_pending_bytes(pu)
    stream = BytesIO(raw)

    disp = "inline" if inline else "attachment"
    filename = (pu.original_filename or f"pending-{pu.token}").replace('"', "").strip()
    mime = (pu.mime_type or "application/octet-stream").split(";")[0].strip()

    headers = {"Content-Disposition": f'{disp}; filename="{filename}"'}
    return StreamingResponse(stream, media_type=mime, headers=headers)
