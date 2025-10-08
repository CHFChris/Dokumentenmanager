from sqlalchemy.orm import Session
from app.repositories.document_repo import get_by_sha_or_name_size

def check_duplicate(db: Session, user_id: int, sha256: str, name: str, size: int) -> dict:
    doc = get_by_sha_or_name_size(db, user_id, sha256, name, size)
    if doc:
        by = "sha256" if doc.sha256 == sha256 else "name_size"
        return {"duplicate": True, "by": by, "existing_id": doc.id}
    return {"duplicate": False}
