# app/web/routes_web.py
from __future__ import annotations

from pathlib import Path
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Form,
    File,
    UploadFile,
    HTTPException,
    Query,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db
from app.core.config import settings
from app.utils.files import ensure_dir, save_stream_to_file, sha256_of_stream
from app.utils.crypto_utils import decrypt_text

from app.services.document_service import (
    dashboard_stats,
    list_documents,
    upload_document,
    remove_document,
    get_document_detail,
    download_response,
    rename_document_service,
)
from app.services.version_service import list_document_versions

from app.services.document_category_service import (
    set_document_categories,
    bulk_set_document_categories,
)

from app.repositories.category_repo import list_categories_for_user
from app.repositories.document_repo import (
    get_document_for_user,
    list_versions_for_document,
    add_version,
    get_version_owned,
    get_document_owned,
)

from app.models.category import Category
from app.models.document import Document

from app.services.auto_tagging import suggest_keywords_for_category

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

FILES_DIR = getattr(settings, "FILES_DIR", "./data/files")


def _user_dir(user_id: int) -> str:
    p = os.path.join(FILES_DIR, str(user_id))
    ensure_dir(p)
    return p


def _ext_of(name: str) -> str:
    _, ext = os.path.splitext(name or "")
    return ext


def _new_storage_path_for_version(user_id: int, base_name: str) -> str:
    base = os.path.basename(base_name)
    stem, ext = os.path.splitext(base)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    candidate = f"{stem}.{stamp}{ext.lower()}"
    target = os.path.join(_user_dir(user_id), candidate)
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


@router.get("/", include_in_schema=False)
def root_to_dashboard() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    stats = dashboard_stats(db, user.id)

    docs_result = list_documents(db, user.id, q=None, limit=10, offset=0)
    docs_list = getattr(docs_result, "items", docs_result)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "docs": docs_list,
            "q": "",
            "error": None,
            "active": "dashboard",
        },
    )


@router.get("/category-keywords", response_class=HTMLResponse)
def category_keywords_page(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    categories = list_categories_for_user(db, user.id)

    return templates.TemplateResponse(
        "category_keywords.html",
        {
            "request": request,
            "user": user,
            "categories": categories,
            "active": "categories",
        },
    )


@router.get("/upload", response_class=HTMLResponse)
def upload_page(
    request: Request,
    user: CurrentUser = Depends(get_current_user_web),
    db: Session = Depends(get_db),
):
    categories = list_categories_for_user(db, user.id)
    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "user": user,
            "active": "upload",
            "categories": categories,
        },
    )


@router.post("/upload-web", include_in_schema=False)
async def upload_web(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    try:
        form = await request.form()
        raw_ids = form.getlist("category_ids")
        category_ids = [int(x) for x in raw_ids if str(x).isdigit()]

        doc = upload_document(
            db=db,
            user_id=user.id,
            original_name=file.filename,
            file_obj=file.file,
            category_id=None,
        )

        set_document_categories(
            db,
            doc_id=doc.id,
            user_id=user.id,
            category_ids=category_ids,
        )

        return RedirectResponse(url="/documents", status_code=303)
    except Exception as ex:
        categories = list_categories_for_user(db, user.id)
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "user": user,
                "error": str(ex),
                "active": "upload",
                "categories": categories,
            },
            status_code=400,
        )


@router.get("/categories/{category_id}", response_class=HTMLResponse)
def category_detail(
    category_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == current_user.id,
        )
        .first()
    )
    if not category:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    suggestions = suggest_keywords_for_category(
        db=db,
        user_id=current_user.id,
        category_id=category_id,
        top_n=15,
    )

    return templates.TemplateResponse(
        "category_detail.html",
        {
            "request": request,
            "user": current_user,
            "category": category,
            "keyword_suggestions": suggestions,
            "active": "categories",
        },
    )


@router.post("/categories/{category_id}/update-keywords-web", include_in_schema=False)
def category_update_keywords_web(
    category_id: int,
    request: Request,
    keywords_text: str = Form(""),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    cleaned = [k.strip() for k in keywords_text.split(",") if k.strip()]

    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == current_user.id,
        )
        .first()
    )
    if not category:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    category.keywords = ", ".join(cleaned) if cleaned else None
    db.add(category)
    db.commit()

    return RedirectResponse(url=f"/categories/{category_id}", status_code=303)


@router.post("/categories/create-web", include_in_schema=False)
def category_create_web(
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    name_clean = (name or "").strip()
    if not name_clean:
        return RedirectResponse(url="/documents", status_code=303)

    exists = (
        db.query(Category)
        .filter(Category.user_id == user.id, Category.name == name_clean)
        .first()
    )
    if exists:
        return RedirectResponse(url="/documents?cat_error=exists", status_code=303)

    cat = Category(user_id=user.id, name=name_clean)
    db.add(cat)
    db.commit()

    return RedirectResponse(url="/documents", status_code=303)


@router.post("/categories/rename-web", include_in_schema=False)
def category_rename_web(
    category_id: int = Form(...),
    new_name: str = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    new_name_clean = (new_name or "").strip()
    if not new_name_clean:
        return RedirectResponse(url="/documents", status_code=303)

    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user.id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    dup = (
        db.query(Category)
        .filter(
            Category.user_id == user.id,
            Category.name == new_name_clean,
            Category.id != category_id,
        )
        .first()
    )
    if dup:
        return RedirectResponse(url="/documents?cat_error=duplicate", status_code=303)

    category.name = new_name_clean
    db.add(category)
    db.commit()

    return RedirectResponse(url="/documents", status_code=303)


@router.post("/categories/delete-web", include_in_schema=False)
def category_delete_web(
    category_id: int = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user.id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    legacy_col = getattr(Document, "category_id", None)
    if legacy_col is not None:
        (
            db.query(Document)
            .filter(Document.owner_user_id == user.id, legacy_col == category_id)
            .update({"category_id": None})
        )

    db.delete(category)
    db.commit()

    return RedirectResponse(url="/documents", status_code=303)


@router.get("/documents", response_class=HTMLResponse)
def documents_page(
    request: Request,
    q: Optional[str] = None,
    category_id: Optional[str] = Query(None),
    filetype: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    try:
        cat_id: Optional[int] = int(category_id) if category_id else None
    except ValueError:
        cat_id = None

    query = (
        db.query(Document)
        .options(selectinload(Document.categories))
        .filter(
            Document.owner_user_id == user.id,
            Document.is_deleted == False,  # noqa: E712
        )
        .order_by(Document.id.desc())
    )

    if cat_id is not None:
        query = (
            query.join(Document.categories)
            .filter(Category.id == cat_id, Category.user_id == user.id)
            .distinct()
        )

    docs_orm: List[Document] = query.limit(200).all()
    filtered_docs_orm: List[Document] = list(docs_orm)

    search_term = (q or "").strip()
    if search_term:
        term_lower = search_term.lower()
        new_list: List[Document] = []
        for d in filtered_docs_orm:
            name_lower = (getattr(d, "filename", "") or "").lower()
            name_match = term_lower in name_lower

            content_match = False
            enc = getattr(d, "ocr_text", None)
            if enc:
                try:
                    plain = decrypt_text(enc)
                except Exception:
                    plain = enc
                try:
                    content_match = bool(plain) and term_lower in str(plain).lower()
                except Exception:
                    content_match = False

            if name_match or content_match:
                new_list.append(d)
        filtered_docs_orm = new_list

    if filetype:
        ext = filetype.lower().lstrip(".")
        new_list: List[Document] = []
        for d in filtered_docs_orm:
            base_name = (getattr(d, "filename", "") or "").lower()
            if base_name.endswith("." + ext):
                new_list.append(d)
        filtered_docs_orm = new_list

    def _parse_date(s: Optional[str]):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s).date()
        except ValueError:
            return None

    df = _parse_date(date_from)
    dt = _parse_date(date_to)

    if df or dt:
        new_list: List[Document] = []
        for d in filtered_docs_orm:
            created = getattr(d, "created_at", None)
            if not created:
                continue
            created_date = created.date()
            if df and created_date < df:
                continue
            if dt and created_date > dt:
                continue
            new_list.append(d)
        filtered_docs_orm = new_list

    filtered_docs = [
        {
            "id": d.id,
            "name": getattr(d, "filename", None) or "",
            "size": getattr(d, "size_bytes", 0) or 0,
            "created_at": getattr(d, "created_at", None),
            "categories": list(getattr(d, "categories", None) or []),
        }
        for d in filtered_docs_orm
    ]

    categories = list_categories_for_user(db, user.id)

    return templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "user": user,
            "docs": filtered_docs,
            "q": q or "",
            "active": "documents",
            "categories": categories,
            "selected_category_id": category_id,
            "filetype": filetype or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
        },
    )


@router.post("/documents/bulk-assign-category", include_in_schema=False)
async def documents_bulk_assign_category(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    form = await request.form()

    raw_docs = form.getlist("doc_ids")
    raw_cats = form.getlist("category_ids")

    doc_ids = [int(x) for x in raw_docs if str(x).isdigit()]
    category_ids = [int(x) for x in raw_cats if str(x).isdigit()]

    if not doc_ids:
        return RedirectResponse(url="/documents?bulk=nodocs", status_code=303)

    bulk_set_document_categories(
        db,
        doc_ids=doc_ids,
        user_id=user.id,
        category_ids=category_ids,
    )

    return RedirectResponse(url="/documents?bulk=ok", status_code=303)


@router.get("/documents/{doc_id}", response_class=HTMLResponse)
def document_detail_page(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    doc = get_document_owned(db, doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    categories = list_categories_for_user(db, user.id)
    versions = list_document_versions(db, doc.id)

    # 5.1: current_category_ids an Template geben
    current_category_ids = [c.id for c in (getattr(doc, "categories", None) or [])]

    return templates.TemplateResponse(
        "document_detail.html",
        {
            "request": request,
            "user": user,
            "doc": doc,
            "categories": categories,
            "versions": versions,
            "current_category_ids": current_category_ids,
        },
    )


@router.get("/documents/{document_id}/view", response_class=HTMLResponse)
def document_view_page(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    doc = get_document_for_user(db, user.id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return templates.TemplateResponse(
        "document_view.html",
        {
            "request": request,
            "user": user,
            "doc": doc,
            "active": "documents",
        },
    )


@router.post("/documents/{doc_id}/set-categories-web", include_in_schema=False)
async def document_set_categories(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    doc = get_document_for_user(db, user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    form = await request.form()
    raw_ids = form.getlist("category_ids")
    category_ids = [int(x) for x in raw_ids if str(x).isdigit()]

    set_document_categories(
        db,
        doc_id=doc_id,
        user_id=user.id,
        category_ids=category_ids,
    )

    return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)


@router.post("/documents/{doc_id}/set-category-web", include_in_schema=False)
def document_set_category(
    doc_id: int,
    category_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    doc = get_document_for_user(db, user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    category_ids = [int(category_id)] if category_id else []

    set_document_categories(
        db,
        doc_id=doc_id,
        user_id=user.id,
        category_ids=category_ids,
    )

    return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)


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


@router.post("/files/{doc_id}/delete-web", include_in_schema=False)
def file_delete_compat(
    doc_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    remove_document(db, user.id, doc_id)
    return RedirectResponse(url="/documents", status_code=303)


@router.get("/documents/{doc_id}/versions", response_class=HTMLResponse)
def document_versions_page(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    doc = get_document_owned(db, doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    versions = list_document_versions(db, doc.id)

    return templates.TemplateResponse(
        "document_versions.html",
        {
            "request": request,
            "user": user,
            "doc": doc,
            "versions": versions,
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
    doc = get_document_for_user(db, user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    base_name = doc.filename or file.filename
    target_path = _new_storage_path_for_version(user.id, base_name)

    size_bytes = save_stream_to_file(file.file, target_path)
    with open(target_path, "rb") as fh:
        sha256_hex = sha256_of_stream(fh)

    mime = getattr(file, "content_type", None) or doc.mime_type

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
    ver = get_version_owned(db, doc_id=doc_id, version_id=version_id, owner_id=user.id)
    if not ver:
        raise HTTPException(status_code=404, detail="Version not found")

    doc = get_document_for_user(db, user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    note = f"Restore from v{getattr(ver, 'version_number', '?')}"

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


@router.get("/security-info", response_class=HTMLResponse)
def security_info_page(
    request: Request,
    user: CurrentUser = Depends(get_current_user_web),
):
    return templates.TemplateResponse(
        "security_info.html",
        {
            "request": request,
            "user": user,
            "active": "security-info",
        },
    )
