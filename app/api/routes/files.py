# app/api/routes/files.py
from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
    Query,
)
from starlette.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO
import os
import mimetypes

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

from app.core.config import settings  # falls anderswo genutzt
from app.utils.crypto_utils import decrypt_bytes, decrypt_text

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


# -------------------------------------------------------------
# Helper: DOCX-Text extrahieren
# -------------------------------------------------------------
def extract_docx_text_from_bytes(data: bytes) -> str:
    """
    Extrahiert einfachen Fließtext aus einer DOCX-Datei.
    Layout ist vereinfacht, aber lesbar.
    """
    if DocxDocument is None:
        return ""
    docx_file = DocxDocument(BytesIO(data))
    parts: list[str] = []
    for p in docx_file.paragraphs:
        text = p.text.strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


# -------------------------------------------------------------
# DETAIL-SEITE (Metadaten + Versionen)
# -------------------------------------------------------------
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


# -------------------------------------------------------------
# VIEWER-SEITE (PDF im iframe oder Text/OCR/DOCX)
# -------------------------------------------------------------
@router.get("/{doc_id}/view")
def document_view_page(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    """
    Viewer-Seite für ein Dokument.

    - PDFs:
        werden über /documents/{id}/download?inline=1 im Browser angezeigt
    - Nicht-PDFs:
        * wenn OCR-Text vorhanden: entschlüsseln und anzeigen
        * sonst: bei DOCX/TXT einfachen Text aus Datei extrahieren
    """
    doc = get_document_owned(db, doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Datei laden (für Text-/DOCX-Vorschau und PDF-Header-Check)
    file_bytes: bytes | None = None
    storage_path = getattr(doc, "storage_path", None)
    if storage_path and os.path.exists(storage_path):
        try:
            with open(storage_path, "rb") as f:
                encrypted_bytes = f.read()
            file_bytes = decrypt_bytes(encrypted_bytes)
        except Exception:
            file_bytes = None

    # Dateiname für Anzeige
    raw_name = (
        getattr(doc, "original_filename", None)
        or getattr(doc, "filename", None)
        or getattr(doc, "name", None)
        or ""
    ).strip()
    name_lower = raw_name.lower()

    # MIME-Typ robust bestimmen
    mime_from_db = getattr(doc, "mime_type", None)
    mime_from_name, _ = mimetypes.guess_type(raw_name)
    mime_raw = mime_from_db or mime_from_name or "application/octet-stream"
    mime_norm = mime_raw.split(";")[0].strip().lower()

    # PDF-Erkennung:
    # 1) MIME "application/pdf" (ohne/mit Charset etc.)
    # 2) Dateiendung .pdf
    # 3) Magic-Header %PDF-
    is_pdf_view = False

    if mime_norm == "application/pdf" or name_lower.endswith(".pdf"):
        is_pdf_view = True

    if (not is_pdf_view) and file_bytes:
        head = file_bytes.lstrip()[:5]
        if head.startswith(b"%PDF-") or head.startswith(b"%pdf-"):
            is_pdf_view = True

    # Klartext / OCR-Text
    ocr_text: str | None = None

    # 1) OCR-Text aus der DB entschlüsseln (falls vorhanden)
    if getattr(doc, "ocr_text", None):
        try:
            ocr_text = decrypt_text(doc.ocr_text)
        except Exception:
            ocr_text = "[Fehler beim Entschlüsseln des OCR-Texts]"

    # 2) Falls kein OCR-Text, aber Datei vorhanden und kein PDF → Text aus Datei
    if (not is_pdf_view) and (not ocr_text) and file_bytes:
        try:
            if name_lower.endswith(".docx"):
                text = extract_docx_text_from_bytes(file_bytes)
                if text:
                    ocr_text = text
            elif name_lower.endswith(".txt"):
                text = file_bytes.decode("utf-8", errors="replace")
                if text.strip():
                    ocr_text = text
        except Exception:
            pass

    print(
        f"[VIEW_DEBUG] id={doc.id}, name={raw_name!r}, mime_raw={mime_raw!r}, "
        f"mime_norm={mime_norm!r}, is_pdf_view={is_pdf_view}, "
        f"has_file_bytes={file_bytes is not None}, has_ocr={ocr_text is not None}"
    )

    return templates.TemplateResponse(
        "document_view.html",
        {
            "request": request,
            "user": user,
            "doc": doc,
            "is_pdf_view": is_pdf_view,
            "ocr_text": ocr_text,
        },
    )


# -------------------------------------------------------------
# DOWNLOAD + INLINE-VORSCHAU
# -------------------------------------------------------------
@router.get("/{doc_id}/download")
def download(
    doc_id: int,
    inline: bool = Query(False),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    """
    Liefert die Datei:
    - inline=true  → Content-Disposition: inline  (für iframe-Vorschau)
    - inline=false → Content-Disposition: attachment (klassischer Download)
    """
    doc = get_document_owned(db, doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")

    if not doc.storage_path or not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    with open(doc.storage_path, "rb") as f:
        encrypted_bytes = f.read()

    try:
        decrypted = decrypt_bytes(encrypted_bytes)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt file")

    stream = BytesIO(decrypted)

    download_name = (
        getattr(doc, "original_filename", None)
        or getattr(doc, "filename", None)
        or f"document-{doc.id}"
    )

    mime = (
        getattr(doc, "mime_type", None)
        or mimetypes.guess_type(download_name)[0]
        or "application/octet-stream"
    )

    disposition = "inline" if inline else "attachment"

    return StreamingResponse(
        stream,
        media_type=mime,
        headers={
            "Content-Disposition": f'{disposition}; filename="{download_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# -------------------------------------------------------------
# VERSIONEN / RENAME
# -------------------------------------------------------------
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


# -------------------------------------------------------------
# ÄHNLICHE DOKUMENTE (OCR)
# -------------------------------------------------------------
@router.get("/{doc_id}/similar")
def similar_documents(
    doc_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_web),
):
    docs = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user.id,
            Document.is_deleted == False,
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

    corpus: list[str] = []
    for d in docs:
        if d.ocr_text:
            corpus.append(decrypt_text(d.ocr_text))
        else:
            corpus.append("")

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
