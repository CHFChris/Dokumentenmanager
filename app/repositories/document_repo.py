from sqlalchemy.orm import Session
from sqlalchemy import select, update, func
from app.models.document import Document
from app.models.document_version import DocumentVersion

def list_documents_for_user(db: Session, user_id: int, q: str | None, limit: int, offset: int):
    stmt = select(Document).where(
        Document.owner_user_id == user_id,
        Document.is_deleted == False
    )
    if q:
        stmt = stmt.where(Document.filename.like(f"%{q}%"))
    total = db.scalar(
        select(func.count()).select_from(
            select(Document.id)
            .where(Document.owner_user_id == user_id, Document.is_deleted == False)
            .subquery()
        )
    ) or 0
    rows = db.scalars(stmt.order_by(Document.id.desc()).limit(limit).offset(offset)).all()
    return rows, total

def create_document_with_version(db: Session, user_id: int, filename: str, storage_path: str,
                                 size_bytes: int, checksum_sha256: str | None, mime_type: str | None):
    doc = Document(
        owner_user_id=user_id,
        filename=filename,
        storage_path=storage_path,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256,
        mime_type=mime_type or None
    )
    db.add(doc)
    db.flush()  # doc.id befüllt

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_path=storage_path,
        checksum_sha256=checksum_sha256
    )
    db.add(ver)
    db.commit()
    db.refresh(doc)
    return doc

def soft_delete_document(db: Session, doc_id: int, user_id: int) -> bool:
    res = db.execute(
        update(Document)
        .where(Document.id == doc_id, Document.owner_user_id == user_id, Document.is_deleted == False)
        .values(is_deleted=True)
    )
    db.commit()
    return res.rowcount > 0
