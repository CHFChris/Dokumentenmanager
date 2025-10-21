# app/api/routes/upload.py
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from typing import Final
from uuid import uuid4
import os

from app.api.deps import get_current_user, CurrentUser  # Bearer/JWT – passt für Swagger & Clients
from app.db.database import get_db
from app.schemas.document import DocumentOut
from app.core.config import settings
from app.utils.files import ensure_dir, sha256_of_stream
from app.repositories.document_repo import create_document_with_version

router = APIRouter(prefix="", tags=["upload"])  # /upload direkt an der Wurzel

# Konfig (optional auch in .env)
MAX_UPLOAD_MB: Final[int] = int(getattr(settings, "MAX_UPLOAD_MB", 50))
ALLOWED_MIME: Final[set[str]] = set(getattr(settings, "ALLOWED_MIME", "").split(",")) if getattr(settings, "ALLOWED_MIME", "") else set()
FILES_DIR: Final[str] = getattr(settings, "FILES_DIR", "./data/files")

def _read_in_chunks_and_hash(src, dst_path: str) -> tuple[int, str]:
    """Streamt Upload -> Datei, berechnet dabei SHA-256. Liefert (size_bytes, sha256_hex)."""
    ensure_dir(os.path.dirname(dst_path))
    hasher_size = 0
    CHUNK = 1024 * 1024
    import hashlib
    h = hashlib.sha256()
    with open(dst_path, "wb") as out:
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            hasher_size += len(chunk)
    return hasher_size, h.hexdigest()

@router.post("/upload", response_model=DocumentOut, status_code=200)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),   # <- erfordert Login (Bearer)
):
    # 1) Basis-Validierungen
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is missing")

    content_type = (file.content_type or "").lower()

    # MIME-Whitelist (optional – nur wenn gesetzt)
    if ALLOWED_MIME and content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported media type '{content_type}' (allowed: {', '.join(sorted(ALLOWED_MIME))})",
        )

    # 2) Zielpfad (user-spezifischer Ordner + eindeutiger Name)
    original_name = os.path.basename(file.filename)
    _, ext = os.path.splitext(original_name)
    safe_ext = ext.lower() if ext else ""
    disk_name = f"{uuid4().hex}{safe_ext}"
    user_dir = os.path.join(FILES_DIR, str(user.id))
    target_path = os.path.join(user_dir, disk_name)

    # 3) Speichern + Hash + Größenlimit
    size_bytes, sha256_hex = _read_in_chunks_and_hash(file.file, target_path)

    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if size_bytes > max_bytes:
        try:
            os.remove(target_path)
        except FileNotFoundError:
            pass
        raise HTTPException(
            status_code=413,
            detail=f"file too large (>{MAX_UPLOAD_MB} MB)"
        )

    # 4) (Optional) User-Quota prüfen – wenn du eine Quota-Tabelle hast, hier einbauen

    # 5) DB-Eintrag (Document + DocumentVersion)
    doc = create_document_with_version(
        db=db,
        user_id=user.id,
        filename=original_name,
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=sha256_hex,
        mime_type=content_type or None,
        note="Initial upload",
    )

    # 6) Antwort
    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256=(doc.checksum_sha256 or ""),
    )
