from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
)
from starlette.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO
import os

from app.core.config import settings
from app.utils.crypto_utils import decrypt_bytes

from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db
from app.models.document import Document
from app.repositories.document_repo import get_document_owned
from app.services.version_service import (
    list_versions,
    upload_new_version,
    restore_version,
    rename_document_creates_version,
)
from app.services.text_similarity import compute_similarities
from app.web.templates import templates

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{doc_id}")
def detail(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    doc = get_document_owned(db, doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")

    _, versions = list_versions(db, user.id, doc_id)

    return templates.TemplateResponse(
        "document_detail.html",
        {
            "request": request,
            "user": user,
            "document": doc,
            "versions": versions,
        },
    )


@router.get("/{doc_id}/download")
def download(
    doc_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    doc = get_document_owned(db, doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")

    if not doc.storage_path or not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    # verschlüsselten Inhalt lesen
    with open(doc.storage_path, "rb") as f:
        encrypted_bytes = f.read()

    try:
        decrypted = decrypt_bytes(encrypted_bytes)
    except Exception:
        # wenn irgendwas mit dem Schlüssel/Daten nicht passt
        raise HTTPException(status_code=500, detail="Failed to decrypt file")

    stream = BytesIO(decrypted)

    download_name = (
        getattr(doc, "original_filename", None)
        or doc.filename
        or f"document-{doc.id}"
    )

    return StreamingResponse(
        stream,
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )



@router.post("/{doc_id}/rename-web")
def rename(
    doc_id: int,
    new_title: str = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    try:
        rename_document_creates_version(db, user.id, doc_id, new_title.strip())
        return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/{doc_id}/upload-version-web")
def upload_version(
    doc_id: int,
    file: UploadFile = File(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    try:
        upload_new_version(db, user.id, doc_id, file.filename, file.file, note=note)
        return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/{doc_id}/restore-web")
def restore(
    doc_id: int,
    version_id: int = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    try:
        restore_version(db, user.id, doc_id, version_id)
        return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/{doc_id}/similar")
def similar_documents(
    doc_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    """
    Liefert ähnliche Dokumente basierend auf OCR-Text
    für alle Dokumente des eingeloggten Users.
    JSON-Response, keine Templates.
    """
    docs = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user.id,
            Document.is_deleted == False,  # noqa: E712
            Document.ocr_text.isnot(None),
        )
        .order_by(Document.id.asc())
        .all()
    )

    id_to_index = {d.id: i for i, d in enumerate(docs)}
    if doc_id not in id_to_index:
        raise HTTPException(
            status_code=404,
            detail="Document not found or no OCR text",
        )

    corpus = [d.ocr_text for d in docs]
    idx = id_to_index[doc_id]

    sims = compute_similarities(corpus, idx, top_k=5)

    result = [
        {
            "id": docs[i].id,
            "filename": docs[i].filename,
            "score": score,
        }
        for i, score in sims
    ]
    return {"base_id": doc_id, "similar": result}
