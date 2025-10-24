# app/web/routes_web.py
from __future__ import annotations

from pathlib import Path
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db

# Services (bestehende, zentrierte Logik)
from app.services.document_service import (
    dashboard_stats,
    list_documents,
    upload_document,
    remove_document,
    get_document_detail,
    download_response,
    rename_document_service,
)

# Repo-Funktionen (für Versionierung)
from app.repositories.document_repo import (
    get_document_for_user,
    list_versions_for_document,
    add_version,
    get_version_owned,
)

# Utils & Settings (für Version-Upload/Restore Dateihandling)
from app.core.config import settings
from app.utils.files import ensure_dir, save_stream_to_file, sha256_of_stream

# -------------------------------------------------------------
# Router & Templates
# -------------------------------------------------------------
router = APIRouter()

# Pfad zu den Templates: /app/web/templates (robust relativ zur Datei)
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

FILES_DIR = getattr(settings, "FILES_DIR", "./data/files")


# -------------------------------------------------------------
# Helper für Versionen
# -------------------------------------------------------------
def _user_dir(user_id: int) -> str:
    p = os.path.join(FILES_DIR, str(user_id))
    ensure_dir(p)
    return p


def _ext_of(name: str) -> str:
    _, ext = os.path.splitext(name or "")
    return ext


def _new_storage_path_for_version(user_id: int, base_name: str) -> str:
    """
    Erzeugt einen neuen Zielpfad für eine Version im User-Verzeichnis.
    Nutzt Zeitstempel + Basename und stellt Kollisionfreiheit her.
    """
    base = os.path.basename(base_name)
    stem, ext = os.path.splitext(base)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    candidate = f"{stem}.{stamp}{ext.lower()}"
    target = os.path.join(_user_dir(user_id), candidate)
    # sehr unwahrscheinlich, aber sicher ist sicher:
    while os.path.exists(target):
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        candidate = f"{stem}.{stamp}{ext.lower()}"
        target = os.path.join(_user_dir(user_id), candidate)
    return target


def _format_versions_list(db_versions) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for v in db_versions:
        out.append(
            {
                "id": v.id,
                "version_number": getattr(v, "version_number", None),
                "size_bytes": getattr(v, "size_bytes", 0),
                "checksum_sha256": getattr(v, "checksum_sha256", "") or "",
                "mime_type": getattr(v, "mime_type", "") or "",
                "note": getattr(v, "note", "") or "",
                "created_at": getattr(v, "created_at", None),
            }
        )
    return out


# -------------------------------------------------------------
# ROOT → Dashboard
# -------------------------------------------------------------
@router.get("/", include_in_schema=False)
def root_to_dashboard() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


# -------------------------------------------------------------
# DASHBOARD (KPIs + letzte Uploads)
# -------------------------------------------------------------
# app/web/routes_web.py
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    stats = dashboard_stats(db, user.id)
    docs = list_documents(db, user.id, q=None, limit=10, offset=0)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,          # ← enthält username (über get_current_user_web)
            "stats": stats,
            "docs": docs,
            "q": "",
            "error": None,
            "active": "dashboard",
        },
    )


# -------------------------------------------------------------
# UPLOAD
# -------------------------------------------------------------
@router.get("/upload", response_class=HTMLResponse)
def upload_page(
    request: Request,
    user: CurrentUser = Depends(get_current_user_web),
):
    return templates.TemplateResponse(
        "upload.html",
        {"request": request, "user": user, "active": "upload"},
    )


@router.post("/upload-web", include_in_schema=False)
async def upload_web(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    try:
        _ = upload_document(db, user.id, file.filename, file.file)
        return RedirectResponse(url="/documents", status_code=303)
    except Exception as ex:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "user": user, "error": str(ex), "active": "upload"},
            status_code=400,
        )


# -------------------------------------------------------------
# DOCUMENTS – Liste & Suche
# -------------------------------------------------------------
@router.get("/documents", response_class=HTMLResponse)
def documents_page(
    request: Request,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    data = list_documents(db, user.id, q=q, limit=200, offset=0)
    return templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "user": user,
            "docs": data,
            "q": q or "",
            "active": "documents",
        },
    )


# -------------------------------------------------------------
# DOCUMENT DETAIL + Basis-Aktionen
# -------------------------------------------------------------
@router.get("/documents/{doc_id}", response_class=HTMLResponse)
def document_detail_page(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    doc = get_document_detail(db, user.id, doc_id)
    return templates.TemplateResponse(
        "document_detail.html",
        {"request": request, "user": user, "doc": doc, "active": "documents"},
    )


@router.get("/documents/{doc_id}/download")
def document_download(
    doc_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    return download_response(db, user.id, doc_id)


@router.post("/documents/{doc_id}/rename-web", include_in_schema=False)
def document_rename(
    doc_id: int,
    new_name: str = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    rename_document_service(db, user.id, doc_id, new_name)
    return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)


@router.post("/documents/{doc_id}/delete-web", include_in_schema=False)
def document_delete(
    doc_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    remove_document(db, user.id, doc_id)
    return RedirectResponse(url="/documents", status_code=303)


# -------------------------------------------------------------
# DOCUMENT VERSIONS – Liste, Upload, Restore
#   UI-Links: /documents/{id}/versions
# -------------------------------------------------------------
@router.get("/documents/{doc_id}/versions", response_class=HTMLResponse)
def document_versions_page(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    # Grunddaten (für Header/Buttons)
    doc = get_document_detail(db, user.id, doc_id)  # dict
    # Versionen aus DB (ORM → dicts fürs Template)
    db_versions = list_versions_for_document(db, doc_id, owner_id=user.id)
    versions = _format_versions_list(db_versions)

    return templates.TemplateResponse(
        "document_versions.html",
        {
            "request": request,
            "user": user,
            "doc": doc,
            "versions": versions,
            "active": "documents",
        },
    )


@router.post("/documents/{doc_id}/upload-version-web", include_in_schema=False)
def document_upload_version(
    doc_id: int,
    file: UploadFile = File(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    """
    Legt eine neue Version an:
    - legt Datei im User-Ordner ab (neuer Pfad, mit Zeitstempel)
    - berechnet Größe + SHA256
    - add_version(): erzeugt Version in DB und spiegelt aktuellen Stand ins Document
    """
    # Ownership sichern & Basismeta holen
    doc = get_document_for_user(db, user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Zielpfad (mit Zeitstempel) im User-Ordner
    base_name = doc.filename or file.filename
    target_path = _new_storage_path_for_version(user.id, base_name)

    # Datei speichern & Hash berechnen
    size_bytes = save_stream_to_file(file.file, target_path)
    with open(target_path, "rb") as fh:
        sha256_hex = sha256_of_stream(fh)

    # MIME aus Dateiname / UploadFile ggf. verwenden
    mime = getattr(file, "content_type", None) or doc.mime_type

    # Repo: neue Version erzeugen (inkl. Spiegelung ins Document)
    add_version(
        db=db,
        doc=doc,
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,
        mime_type=mime,
        note=note or "Uploaded new version",
    )

    return RedirectResponse(url=f"/documents/{doc_id}/versions", status_code=303)


@router.post("/documents/{doc_id}/restore-version-web", include_in_schema=False)
def document_restore_version(
    doc_id: int,
    version_id: int = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    """
    Stellt eine frühere Version wieder her, indem eine NEUE Version angelegt wird,
    die auf exakt denselben Storage-Pfad zeigt (keine Dateiduplizierung).
    """
    # Version + Ownership prüfen
    ver = get_version_owned(db, doc_id=doc_id, version_id=version_id, owner_id=user.id)
    if not ver:
        raise HTTPException(status_code=404, detail="Version not found")

    # Zugehöriges Dokument laden
    doc = get_document_for_user(db, user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Wiederherstellungs-Note
    note = f"Restore from v{getattr(ver, 'version_number', '?')}"

    # Neue Version, die auf denselben Pfad zeigt (effizient & nachvollziehbar)
    add_version(
        db=db,
        doc=doc,
        storage_path=ver.storage_path,
        size_bytes=ver.size_bytes,
        checksum_sha256=ver.checksum_sha256,
        mime_type=ver.mime_type,
        note=note,
    )

    return RedirectResponse(url=f"/documents/{doc_id}/versions", status_code=303)


# -------------------------------------------------------------
# SEPARATE SEARCH-SEITE (optional)
# -------------------------------------------------------------
@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    results = list_documents(db, user.id, q=q, limit=200, offset=0) if q else None
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "user": user,
            "q": q or "",
            "results": results,
            "active": "search",
        },
    )
