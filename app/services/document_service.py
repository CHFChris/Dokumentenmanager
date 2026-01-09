# app/services/document_service.py
from __future__ import annotations

import os
import uuid
import mimetypes
from datetime import datetime, timezone
from io import BytesIO
from tempfile import NamedTemporaryFile
from typing import BinaryIO, Optional, List, Dict
from urllib.parse import quote

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload
from starlette.responses import StreamingResponse

from app.core.config import settings
from app.models.category import Category
from app.models.document import Document
from app.repositories.document_repo import (
    count_documents_for_user,
    create_document_with_version,
    get_document_for_user,
    get_document_owned as _get_document_owned_legacy,
    recent_uploads_count_week,
    recent_uploads_for_user,
    set_ocr_text_for_document,
    soft_delete_document,
    storage_used_for_user,
    update_document_name_and_path,
)
from app.schemas.document import DocumentListOut, DocumentOut
from app.services.auto_tagging import suggest_categories_for_document
from app.services.document_category_service import set_document_categories
from app.services.ocr_service import ocr_and_clean
from app.utils.crypto_utils import (
    decrypt_bytes,
    decrypt_text,
    encrypt_bytes,
    compute_integrity_tag,
)
from app.utils.files import ensure_dir, save_stream_to_file, sha256_of_stream

# ------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------
FILES_DIR = getattr(settings, "FILES_DIR", "./data/files")

SIMPLE_STOPWORDS = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einer", "einem", "einen",
    "den", "im", "in", "ist", "sind", "war", "waren", "von", "mit", "auf", "für",
    "an", "am", "als", "zu", "zum", "zur", "bei", "aus", "dem",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "at", "by",
    "this", "that", "these", "those", "it", "its", "be", "was", "were", "are",
}

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _sanitize_display_name(name: str) -> str:
    name = (name or "").strip()
    name = os.path.basename(name)
    bad = {"/", "\\", "\0"}
    if any(ch in name for ch in bad):
        name = name.replace("/", "_").replace("\\", "_").replace("\0", "")
    return name[:255] or "unnamed"


def _uuid_disk_name_with_ext(original_name: str) -> str:
    _, ext = os.path.splitext(original_name or "")
    ext = ext.lower()
    return f"{uuid.uuid4().hex}{ext}"


def _unique_target_path(base_dir: str, original_name_for_ext: str) -> tuple[str, str]:
    ensure_dir(base_dir)
    disk_name = _uuid_disk_name_with_ext(original_name_for_ext)
    target_path = os.path.join(base_dir, disk_name)
    while os.path.exists(target_path):
        disk_name = _uuid_disk_name_with_ext(original_name_for_ext)
        target_path = os.path.join(base_dir, disk_name)
    return disk_name, target_path


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    raw_tokens = text.lower().split()
    tokens: list[str] = []
    for t in raw_tokens:
        t = t.strip(".,;:!?()[]{}\"'`<>|/\\+-=_")
        if not t:
            continue
        if len(t) < 3:
            continue
        if t in SIMPLE_STOPWORDS:
            continue
        tokens.append(t)
    return tokens


def _score_document(title: str, body: str, query_tokens: List[str]) -> int:
    if not query_tokens:
        return 0


def _category_ids(doc: Document) -> List[int]:
    cats = getattr(doc, "categories", None) or []
    out: List[int] = []
    for c in cats:
        cid = getattr(c, "id", None)
        if isinstance(cid, int):
            out.append(cid)
    return out


def _decrypt_ocr_text_if_needed(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return decrypt_text(value)
    except Exception:
        return ""


def _categories_to_string(doc: Document) -> Optional[str]:
    cats = getattr(doc, "categories", None) or []
    names = [c.name for c in cats if getattr(c, "name", None)]
    return ", ".join(names) if names else None


def _category_ids(doc: Document) -> List[int]:
    cats = getattr(doc, "categories", None) or []
    out: List[int] = []
    for c in cats:
        cid = getattr(c, "id", None)
        if isinstance(cid, int):
            out.append(cid)
    return out


# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------
def dashboard_stats(db: Session, user_id: int) -> dict:
    total = count_documents_for_user(db, user_id)
    storage = storage_used_for_user(db, user_id)
    recent_week = recent_uploads_count_week(db, user_id)
    recent_items = recent_uploads_for_user(db, user_id, limit=5)

    most_words = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.ocr_text.isnot(None),
        )
        .all()
    )

    word_stats = [{"id": d.id, "words": len((d.ocr_text or "").split())} for d in most_words]

    return {
        "total": total,
        "storage_bytes": storage,
        "recent_week": recent_week,
        "recent_items": recent_items,
        "word_stats": word_stats,
    }


# ------------------------------------------------------------
# Listing / Suche
# ------------------------------------------------------------
def list_documents(
    db: Session,
    user_id: int,
    q: str | None,
    limit: int,
    offset: int,
    category_id: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    mime_startswith: str | None = None,
    only_with_ocr: bool = False,
) -> DocumentListOut:
    query = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.is_deleted == False,  # noqa: E712
        )
    )

    if q:
        return search_documents_advanced(
            db=db,
            user_id=user_id,
            q=q,
            limit=limit,
            offset=offset,
            category_id=category_id,
            created_from=created_from,
            created_to=created_to,
            mime_startswith=mime_startswith,
            only_with_ocr=only_with_ocr,
        )

    if category_id is not None:
        query = (
            query.join(Document.categories)
            .filter(
                Category.id == category_id,
                Category.user_id == user_id,
            )
            .distinct()
        )

    if created_from is not None:
        query = query.filter(Document.created_at >= created_from)

    if created_to is not None:
        query = query.filter(Document.created_at <= created_to)

    if mime_startswith:
        query = query.filter(Document.mime_type.like(f"{mime_startswith}%"))

    if only_with_ocr:
        query = query.filter(Document.ocr_text.isnot(None))

    total = query.count()

    rows = (
        query.order_by(Document.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        DocumentOut(
            id=r.id,
            name=r.filename,
            size=r.size_bytes,
            sha256="",
            created_at=getattr(r, "created_at", None),
            category=_categories_to_string(r),
            category_ids=_category_ids(r),
            category_names=[c.name for c in (getattr(r, "categories", None) or [])],
        )
        for r in rows
    ]
    return DocumentListOut(items=items, total=total)


def search_documents_advanced(
    db: Session,
    user_id: int,
    q: str,
    limit: int,
    offset: int,
    category_id: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    mime_startswith: str | None = None,
    only_with_ocr: bool = False,
) -> DocumentListOut:
    if not q:
        return DocumentListOut(items=[], total=0)

    query_tokens = _tokenize(q)
    if not query_tokens:
        return DocumentListOut(items=[], total=0)

    base_query = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.is_deleted == False,  # noqa: E712
        )
        .options(selectinload(Document.categories), selectinload(Document.versions))
    )

    if category_id is not None:
        base_query = (
            base_query.join(Document.categories)
            .filter(
                Category.id == category_id,
                Category.user_id == user_id,
            )
            .distinct()
        )

    if created_from is not None:
        base_query = base_query.filter(Document.created_at >= created_from)

    if created_to is not None:
        base_query = base_query.filter(Document.created_at <= created_to)

    if mime_startswith:
        base_query = base_query.filter(Document.mime_type.like(f"{mime_startswith}%"))

    if only_with_ocr:
        base_query = base_query.filter(Document.ocr_text.isnot(None))

    candidates: list[Document] = base_query.all()

    scored: list[dict] = []
    now = datetime.now(timezone.utc)

    for d in candidates:
        title = (d.filename or "").strip()

        body_plain = ""
        enc = getattr(d, "ocr_text", None)
        if enc:
            try:
                body_plain = decrypt_text(enc) or ""
            except Exception:
                body_plain = ""

        # Trefferhaeufigkeit (title * 3, body * 1)
        title_l = title.lower()
        body_l = body_plain.lower()
        hit_score = 0
        for tok in query_tokens:
            if not tok:
                continue
            hit_score += title_l.count(tok) * 3
            hit_score += body_l.count(tok)

        if hit_score <= 0:
            continue

        # Aktualitaet: max(created_at, version.updated_at/created_at)
        last_upd = getattr(d, "created_at", None)
        for v in (getattr(d, "versions", None) or []):
            cand = getattr(v, "updated_at", None) or getattr(v, "created_at", None)
            if cand and (last_upd is None or cand > last_upd):
                last_upd = cand

        if last_upd is None:
            last_upd = datetime.fromtimestamp(0, tz=timezone.utc)
        elif last_upd.tzinfo is None:
            last_upd = last_upd.replace(tzinfo=timezone.utc)

        age_days = max(0, int((now - last_upd).total_seconds() // 86400))
        recency_bonus = max(0, 30 - min(age_days, 30))  # 0..30

        score = hit_score * 100 + recency_bonus
        scored.append({"doc": d, "score": score, "last_upd": last_upd})

    scored.sort(key=lambda x: (x["score"], x["last_upd"], x["doc"].id), reverse=True)

    total = len(scored)
    sliced = scored[offset: offset + limit]

    items = [
        DocumentOut(
            id=e["doc"].id,
            name=e["doc"].filename,
            size=e["doc"].size_bytes,
            sha256="",
            created_at=getattr(e["doc"], "created_at", None),
            category=_categories_to_string(e["doc"]),
            category_ids=_category_ids(e["doc"]),
            category_names=[c.name for c in (getattr(e["doc"], "categories", None) or [])],
        )
        for e in sliced
    ]

    return DocumentListOut(items=items, total=total)


# ------------------------------------------------------------
# Upload (API /documents/upload)
# ------------------------------------------------------------
def upload_document(
    db: Session,
    user_id: int,
    original_name: str,
    file_obj: BinaryIO,
    content_type: Optional[str] = None,
    category_id: Optional[int] = None,
) -> DocumentOut:
    """Upload ueber die /documents/upload-API.

    Speichert eine hochgeladene Datei inkl. Metadaten in der DB:
    - Name: original/Anzeige (documents.filename + documents.original_filename)
    - Groesse: documents.size_bytes
    - Typ: documents.mime_type
    - Owner: documents.owner_user_id
    - Hash: documents.checksum_sha256 (HMAC-SHA256 Integritaetstag)

    Zusaetzlich wird ein eindeutiger interner File-Identifier gesetzt:
    - documents.stored_name (uuid4 hex, UNIQUE)
    """

    original_name = os.path.basename((original_name or "").strip()) or "unnamed"
    display_name = _sanitize_display_name(original_name)

    # MIME bestimmen (UploadFile.content_type -> Fallback ueber Extension)
    mime = (content_type or "").split(";")[0].strip().lower()
    if (not mime) or (mime == "application/octet-stream"):
        guessed, _ = mimetypes.guess_type(display_name)
        if guessed:
            mime = guessed.lower()
    mime_type = mime or None

    # Datei lesen (Klartext)
    raw_bytes = file_obj.read() if file_obj else b""
    if raw_bytes is None:
        raw_bytes = b""
    size_bytes = len(raw_bytes)
    if size_bytes <= 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Hash (Integritaet) ueber Klartext
    integrity_tag = compute_integrity_tag(raw_bytes)

    # Verschluesseln + speichern
    encrypted_bytes = encrypt_bytes(raw_bytes)

    user_dir = os.path.join(FILES_DIR, str(user_id))
    ensure_dir(user_dir)

    stored_name = uuid.uuid4().hex
    target_path = os.path.join(user_dir, stored_name)
    while os.path.exists(target_path):
        stored_name = uuid.uuid4().hex
        target_path = os.path.join(user_dir, stored_name)

    with open(target_path, "wb") as f:
        f.write(encrypted_bytes)

    # DB: Document + Version 1 (inkl. Metadaten)
    doc = create_document_with_version(
        db=db,
        user_id=user_id,
        filename=display_name,
        storage_path=target_path,
        size_bytes=size_bytes,
        checksum_sha256=integrity_tag,
        mime_type=mime_type,
        note="Initial upload",
        original_filename=original_name,
        stored_name=stored_name,
    )

    # (Legacy) Single-Kategorie setzen (wird als Many-to-Many gespeichert)
    if category_id is not None:
        cat = (
            db.query(Category)
            .filter(Category.user_id == user_id, Category.id == category_id)
            .first()
        )
        if cat:
            current = get_document_for_user(db, user_id, doc.id) or doc
            existing_ids: List[int] = []
            for c in (getattr(current, "categories", None) or []):
                cid = getattr(c, "id", None)
                if isinstance(cid, int):
                    existing_ids.append(cid)

            new_ids = list(dict.fromkeys(existing_ids + [cat.id]))

            set_document_categories(
                db,
                doc_id=doc.id,
                user_id=user_id,
                category_ids=new_ids,
            )

    if category_id is not None:
        cat = (
            db.query(Category)
            .filter(Category.user_id == user_id, Category.id == category_id)
            .first()
        )
        if cat:
            current = get_document_for_user(db, user_id, doc.id) or doc
            existing_ids: List[int] = []
            for c in (getattr(current, "categories", None) or []):
                cid = getattr(c, "id", None)
                if isinstance(cid, int):
                    existing_ids.append(cid)

            new_ids = list(dict.fromkeys(existing_ids + [cat.id]))

            set_document_categories(
                db,
                doc_id=doc.id,
                user_id=user_id,
                category_ids=new_ids,
            )

    return DocumentOut(
        id=doc.id,
        name=doc.filename,
        size=doc.size_bytes,
        sha256="",
        created_at=getattr(doc, "created_at", None),
        category=_categories_to_string(doc),
        category_ids=_category_ids(doc),
        category_names=[c.name for c in (getattr(doc, "categories", None) or [])],
    )


# ------------------------------------------------------------
# Detail / Download
# ------------------------------------------------------------
def get_document_detail(db: Session, user_id: int, doc_id: int) -> dict:
    doc = (
        db.query(Document)
        .filter(Document.owner_user_id == user_id, Document.id == doc_id)
        .options(selectinload(Document.categories))
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "name": doc.filename,
        "size": doc.size_bytes,
        "sha256": "",
        "mime": doc.mime_type or "",
        "created_at": getattr(doc, "created_at", None),
        "storage_path": doc.storage_path,
        "ext": (doc.filename.rsplit(".", 1)[-1].upper()) if "." in (doc.filename or "") else "FILE",
        "category_ids": _category_ids(doc),
        "category_names": [c.name for c in (getattr(doc, "categories", None) or [])],
        "category": _categories_to_string(doc),
    }


def _resolve_existing_file_path(user_id: int, doc: Document) -> Optional[str]:
    candidates: list[str] = []

    def add(p: Optional[str]) -> None:
        if p and p not in candidates:
            candidates.append(p)

    sp = getattr(doc, "storage_path", None)
    add(sp)

    if sp:
        add(os.path.normpath(sp))
        add(os.path.normpath(sp.replace("\\", "/")))

        if not os.path.isabs(sp):
            add(os.path.abspath(sp))
            add(os.path.abspath(os.path.normpath(sp)))
            add(os.path.abspath(os.path.join(os.getcwd(), sp.lstrip("./\\"))))

    stored = getattr(doc, "stored_name", None)
    if stored:
        add(os.path.join(FILES_DIR, str(user_id), stored))
        add(os.path.abspath(os.path.join(FILES_DIR, str(user_id), stored)))

    for p in candidates:
        try:
            if p and os.path.exists(p):
                return p
        except Exception:
            continue

    return None


def download_response(db: Session, user_id: int, doc_id: int, inline: bool = False) -> StreamingResponse:
    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    path = _resolve_existing_file_path(user_id, doc)
    if not path:
        raise HTTPException(status_code=404, detail="Stored file missing on disk")

    with open(path, "rb") as fh:
        encrypted = fh.read()

    try:
        decrypted = decrypt_bytes(encrypted)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt file")

    stream = BytesIO(decrypted)

    filename = getattr(doc, "original_filename", None) or doc.filename or f"document-{doc.id}"
    filename = filename.replace('"', "").strip() or f"document-{doc.id}"

    disp = "inline" if inline else "attachment"
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").replace('"', "").strip()
    if not ascii_fallback:
        ascii_fallback = f"document-{doc.id}"

    cd = f"{disp}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"

    return StreamingResponse(
        stream,
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": cd,
            "X-Content-Type-Options": "nosniff",
        },
    )


# ------------------------------------------------------------
# Rename (Dateisystem + DB)
# ------------------------------------------------------------
def rename_document_service(db: Session, user_id: int, doc_id: int, new_name: str) -> None:
    new_display_name = _sanitize_display_name(new_name)
    if not new_display_name:
        raise HTTPException(status_code=400, detail="Invalid file name")

    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    old_path = doc.storage_path
    if not old_path or not os.path.exists(old_path):
        raise HTTPException(status_code=409, detail="Stored file missing on disk")

    old_ext = os.path.splitext(doc.filename)[1]
    base_new = new_display_name if os.path.splitext(new_display_name)[1] else f"{new_display_name}{old_ext}"

    user_dir = os.path.join(FILES_DIR, str(user_id))
    ensure_dir(user_dir)
    _, new_path = _unique_target_path(user_dir, base_new)

    os.replace(old_path, new_path)

    ok = update_document_name_and_path(
        db=db,
        user_id=user_id,
        doc_id=doc_id,
        new_filename=new_display_name,
        new_storage_path=new_path,
    )
    if not ok:
        try:
            os.replace(new_path, old_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to update database")


# ------------------------------------------------------------
# Delete (Soft)
# ------------------------------------------------------------
def remove_document(db: Session, user_id: int, doc_id: int) -> bool:
    return soft_delete_document(db, doc_id, user_id)


# ------------------------------------------------------------
# OCR + Auto-Kategorien (Top-N) fuer verschluesselte Dateien
# ------------------------------------------------------------
def run_ocr_and_auto_category(
    db: Session,
    user_id: int,
    doc: Document,
) -> None:
    if not doc.storage_path or not os.path.exists(doc.storage_path):
        print(f"[OCR] storage_path fehlt oder existiert nicht: {doc.storage_path}")
        return

    print(f"[UPLOAD] Starte run_ocr_and_auto_category fuer Doc {doc.id}")
    print(f"[OCR] Start fuer Doc {doc.id}, path={doc.storage_path}")

    try:
        with open(doc.storage_path, "rb") as fh:
            encrypted = fh.read()
        decrypted = decrypt_bytes(encrypted)
        print(f"[OCR] entschluesselte Bytes: {len(decrypted)}")
    except Exception as exc:
        print(f"[OCR] Fehler beim Entschluesseln: {exc!r}")
        return

    name_source = getattr(doc, "original_filename", None) or doc.filename or ""
    suffix = ""
    if "." in name_source:
        suffix = "." + name_source.rsplit(".", 1)[-1].lower()

    tmp = NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(decrypted)
        tmp.flush()
        tmp_path = tmp.name
    finally:
        tmp.close()

    print(f"[OCR] Tempfile: {tmp_path}, suffix={suffix}")

    try:
        ocr_plain = ocr_and_clean(path=tmp_path, lang="deu+eng", dpi=300)
        ocr_plain = (ocr_plain or "").strip()
        print(f"[OCR] Ergebnis-Laenge: {len(ocr_plain)}")
    except Exception as exc:
        print(f"[OCR] Fehler in ocr_and_clean: {exc!r}")
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if not ocr_plain:
        print("[OCR] Kein Text erkannt, abbrechen")
        return

    try:
        set_ocr_text_for_document(
            db=db,
            user_id=user_id,
            doc_id=doc.id,
            ocr_plaintext=ocr_plain,
        )
        print(f"[OCR] OCR-Text in DB gespeichert fuer Doc {doc.id}")
    except Exception as exc:
        print(f"[OCR] Fehler beim Schreiben des OCR-Textes in die DB: {exc!r}")
        return

    try:
        cats = suggest_categories_for_document(
            db=db,
            user_id=user_id,
            ocr_plaintext=ocr_plain,
            min_score=1,
            top_k=3,
        )
    except Exception as exc:
        print(f"[OCR] Fehler bei suggest_categories_for_document: {exc!r}")
        return

    if not cats:
        print("[OCR] Keine Kategorie gefunden (Top-N)")
        return

    cat_ids = [c.id for c in cats if isinstance(getattr(c, "id", None), int)]
    print(f"[OCR] Auto-Kategorien gefunden: {cat_ids} fuer Doc {doc.id}")

    try:
        current_doc = get_document_for_user(db, user_id, doc.id) or doc
        existing_ids: List[int] = []
        for c in (getattr(current_doc, "categories", None) or []):
            cid = getattr(c, "id", None)
            if isinstance(cid, int):
                existing_ids.append(cid)

        new_ids = list(dict.fromkeys(existing_ids + cat_ids))

        set_document_categories(
            db,
            doc_id=doc.id,
            user_id=user_id,
            category_ids=new_ids,
        )

        print(f"[OCR] Kategorien {new_ids} an Doc {doc.id} gespeichert")
    except Exception as exc:
        print(f"[OCR] Fehler beim Speichern der Kategorien: {exc!r}")
        db.rollback()
        return


# ------------------------------------------------------------
# Legacy-Wrapper (rueckwaertskompatibel)
# ------------------------------------------------------------
def get_owned_or_404(db: Session, user_id: int, doc_id: int):
    doc = get_document_for_user(db, user_id, doc_id)
    if not doc:
        raise ValueError("NOT_FOUND_OR_FORBIDDEN")
    return doc


def delete_owned_document(db: Session, user_id: int, doc_id: int) -> bool:
    _ = get_owned_or_404(db, user_id, doc_id)
    return soft_delete_document(db, doc_id, user_id)
