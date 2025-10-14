# app/web/routes_web.py
from pathlib import Path
from fastapi import APIRouter, Depends, Request, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db
from app.services.document_service import (
    dashboard_stats,
    list_documents,
    upload_document,
    remove_document
)

# Router
router = APIRouter()

# Pfad zu den Templates: /app/web/templates
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ----------------------------
# ROOT → Weiterleitung Dashboard
# ----------------------------
@router.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard", status_code=302)


# ----------------------------
# DASHBOARD
# ----------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db)
):
    stats = dashboard_stats(db, user.id)
    recent = list_documents(db, user.id, q=None, limit=5, offset=0)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "stats": stats, "recent": recent, "active": "dashboard"}
    )


# ----------------------------
# UPLOAD
# ----------------------------
@router.get("/upload", response_class=HTMLResponse)
def upload_page(
    request: Request,
    user: CurrentUser = Depends(get_current_user_web)
):
    return templates.TemplateResponse(
        "upload.html",
        {"request": request, "user": user, "active": "upload"}
    )


@router.post("/upload", include_in_schema=False)
def upload_action(
    request: Request,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db)
):
    _ = upload_document(db, user.id, file.filename, file.file)
    return RedirectResponse(url="/documents", status_code=303)


# ----------------------------
# DOCUMENTS
# ----------------------------
@router.get("/documents", response_class=HTMLResponse)
def documents_page(
    request: Request,
    q: str | None = None,
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db)
):
    docs = list_documents(db, user.id, q=q, limit=200, offset=0)
    return templates.TemplateResponse(
        "documents.html",
        {"request": request, "user": user, "docs": docs, "q": q or "", "active": "documents"}
    )


@router.post("/documents/{doc_id}/delete", include_in_schema=False)
def documents_delete(
    doc_id: int,
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db)
):
    remove_document(db, user.id, doc_id)
    return RedirectResponse(url="/documents", status_code=303)


# ----------------------------
# SEARCH
# ----------------------------
@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str | None = None,
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db)
):
    results = list_documents(db, user.id, q=q, limit=200, offset=0) if q else None
    return templates.TemplateResponse(
        "search.html",
        {"request": request, "user": user, "q": q or "", "results": results, "active": "search"}
    )
