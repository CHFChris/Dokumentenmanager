from pydantic import BaseModel
from typing import List

class DocumentOut(BaseModel):
    id: int
    name: str          # <- mapped aus documents.filename
    size: int          # <- mapped aus documents.size_bytes
    sha256: str | None # <- mapped aus documents.checksum_sha256

    class Config:
        from_attributes = True

class DocumentListOut(BaseModel):
    items: List[DocumentOut]
    total: int
