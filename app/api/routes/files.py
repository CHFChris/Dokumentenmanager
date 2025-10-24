# app/api/routes/documents.py
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session

# Wichtig: Web-Cookie-Auth verwenden (oder auf get_current_user_api wechseln, wenn Bearer-Auth gewünscht)
from app.api.deps import get_current_user_web as get_current_user, CurrentUser

from app.db.database import get_db
from app.schemas.document import DocumentListOut, DocumentOut
from app.services.document_service import (
    list_documents,
    upload_document,
    remove_document,
    get_document_detail,
    download_response,
    rename_document_service,
)

router = APIRouter(prefix="/documents", tags=["documents"])


# ------------------------------------------------------------
# Listing / Suche
# ------------------------------------------------------------
@router.get("", response_model=DocumentListOut)
async def list_files(
    q: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_documents(db, user.id, q, limit, offset)


# ------------------------------------------------------------
# Upload
# ------------------------------------------------------------
@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return upload_document(db, user.id, file.filename, file.file)


# ------------------------------------------------------------
# Detail
# ------------------------------------------------------------
@router.get("/{doc_id}")
async def document_detail(
    doc_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_document_detail(db, user.id, doc_id)


# ------------------------------------------------------------
# Download
# ------------------------------------------------------------
@router.get("/{doc_id}/download")
async def download(
    doc_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return download_response(db, user.id, doc_id)


# ------------------------------------------------------------
# Rename
# ------------------------------------------------------------
@router.post("/{doc_id}/rename")
async def rename(
    doc_id: int,
    new_name: str = Query(..., description="Neuer Dateiname"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Bennennt ein Dokument um.
    - Behält die Dateiendung, wenn keine angegeben
    - Prüft Dateikollisionen
    - Aktualisiert DB & verschiebt physisch
    """
    rename_document_service(db, user.id, doc_id, new_name)
    return {"status": "ok"}


# ------------------------------------------------------------
# Delete
# ------------------------------------------------------------
@router.delete("/{doc_id}", status_code=204)
async def remove(
    doc_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ok = remove_document(db, user.id, doc_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Document not found"},
        )
    return None
