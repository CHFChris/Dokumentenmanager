from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

class DocumentOut(BaseModel):
    id: int
    name: str
    size: int
    sha256: str
    created_at: Optional[datetime] = None
    category: Optional[str] = None

class DocumentListOut(BaseModel):
    items: List[DocumentOut]
    total: int
