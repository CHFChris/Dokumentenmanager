# app/web/routes_web.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db
from app.services.document_service import (
    dashboard_stats,
    list_documents,
    upload_document,
    remove_document,
    get_document_detail,
    download_response,
    rename_document_service,
)

# -------------------------------------------------------------------
# Router & Templates
# -------------------------------------------------------------------
router = APIRouter()

# Pfad zu den Templates: /app/web/templates (robust relativ zur Datei)
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# -------------------------------------------------------------------
# ROOT → Dashboard
# -------------------------------------------------------------------
@router.get("/", include_in_schema=False)
def root_to_dashboard() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


# -------------------------------------------------------------------
# DASHBOARD (KPIs + letzte Uploads)
# -------------------------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    stats = dashboard_stats(db, user.id)
    # kleine Liste für die Karte/Tabelle
    docs = list_documents(db, user.id, q=None, limit=10, offset=0)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "docs": docs,
            "q": "",
            "error": None,
            "active": "dashboard",
        },
    )


# -------------------------------------------------------------------
# UPLOAD
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# DOCUMENTS – Liste & Suche
# -------------------------------------------------------------------
@router.get("/documents", response_class=HTMLResponse)
def documents_page(
    request: Request,
    q: str | None = None,
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


# -------------------------------------------------------------------
# DOCUMENT DETAIL + Aktionen
# -------------------------------------------------------------------
@router.get("/documents/{doc_id}", response_class=HTMLResponse)
def document_detail(
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


# -------------------------------------------------------------------
# SEPARATE SEARCH-SEITE (optional)
# -------------------------------------------------------------------
@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str | None = None,
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
