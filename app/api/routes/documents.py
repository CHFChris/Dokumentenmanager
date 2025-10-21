# app/api/routes/documents.py  (neue, klare Gruppe)
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from starlette.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db
from app.services.version_service import (
    list_versions, upload_new_version, restore_version, rename_document_creates_version
)
from app.repositories.document_repo import get_document_owned

router = APIRouter(prefix="/documents", tags=["documents"])

@router.get("/{doc_id}")
def detail(doc_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user_web)):
    doc = get_document_owned(db, doc_id, user.id)
    if not doc:
        raise HTTPException(404, "Not found")
    _, versions = list_versions(db, user.id, doc_id)
    # Template-View:
    from app.web.templates import templates  # oder injiziere global
    return templates.TemplateResponse("document_detail.html", {
        "request": ...,  # in Web-Router lösen, siehe unten
    })

@router.get("/{doc_id}/download")
def download(doc_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user_web)):
    doc = get_document_owned(db, doc_id, user.id)
    if not doc:
        raise HTTPException(404, "Not found")
    return FileResponse(path=doc.storage_path, filename=doc.filename, headers={"X-Content-Type-Options": "nosniff"})

@router.post("/{doc_id}/rename-web")
def rename(doc_id: int, new_title: str = Form(...), db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user_web)):
    try:
        rename_document_creates_version(db, user.id, doc_id, new_title.strip())
        return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)
    except ValueError:
        raise HTTPException(404, "Not found")

@router.post("/{doc_id}/upload-version-web")
def upload_version(doc_id: int, file: UploadFile = File(...), note: str = Form(""), db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user_web)):
    try:
        upload_new_version(db, user.id, doc_id, file.filename, file.file, note=note)
        return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)
    except ValueError:
        raise HTTPException(404, "Not found")

@router.post("/{doc_id}/restore-web")
def restore(doc_id: int, version_id: int = Form(...), db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user_web)):
    try:
        restore_version(db, user.id, doc_id, version_id)
        return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)
    except ValueError:
        raise HTTPException(404, "Not found")
