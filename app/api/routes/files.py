from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, CurrentUser
from app.schemas.document import DocumentListOut, DocumentOut
from app.services.document_service import upload_document, list_documents, remove_document
from app.db.database import get_db

router = APIRouter(prefix="/files", tags=["files"])

@router.get("", response_model=DocumentListOut)
async def list_files(
    q: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return list_documents(db, user.id, q, limit, offset)

@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return upload_document(db, user.id, file.filename, file.file)

@router.delete("/{doc_id}", status_code=204)
async def remove(doc_id: int, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ok = remove_document(db, user.id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Document not found"})
    return None
