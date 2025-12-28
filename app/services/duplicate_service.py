from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.document_repo import get_by_sha_or_name_size


class DuplicateDocumentError(Exception):
    """Upload ist ein Duplikat zu einem bestehenden Dokument."""

    def __init__(self, existing_id: int, by: str, message: Optional[str] = None) -> None:
        self.existing_id = int(existing_id)
        self.by = str(by)
        super().__init__(
            message
            or f"Duplikat erkannt ({self.by}). Bestehendes Dokument: {self.existing_id}."
        )


def find_duplicate(
    db: Session,
    user_id: int,
    sha256: Optional[str],
    name: Optional[str],
    size: Optional[int],
) -> Tuple[Optional[Document], Optional[str]]:
    """Sucht ein Duplikat fuer den User."""

    doc = get_by_sha_or_name_size(db, user_id, sha256, name, size)
    if not doc:
        return None, None

    sha_norm = (sha256 or "").strip()
    if sha_norm and (getattr(doc, "checksum_sha256", None) == sha_norm):
        return doc, "sha256"

    return doc, "name_size"
