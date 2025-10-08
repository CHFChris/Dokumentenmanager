from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, CurrentUser
from app.schemas.document import DuplicateCheckIn, DuplicateCheckOut
from app.services.duplicate_service import check_duplicate
from app.db.database import get_db

router = APIRouter(prefix="/files", tags=["duplicates"])

@router.post("/duplicate-check", response_model=DuplicateCheckOut)
def duplicate_check(body: DuplicateCheckIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return check_duplicate(db, user.id, body.sha256, body.name, body.size)
