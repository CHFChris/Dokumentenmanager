# app/api/routes/users.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

# Importiere die kombinierte Funktion (akzeptiert Cookie oder Bearer)
from app.api.deps import get_current_user_any, CurrentUser
from app.db.database import get_db
from app.schemas.auth import UserOut

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserOut)
def me(
    user: CurrentUser = Depends(get_current_user_any),
    db: Session = Depends(get_db)
):
    """
    Gibt den aktuell eingeloggten Benutzer zurück.
    Funktioniert sowohl mit:
      - JWT im HttpOnly Cookie (Browser-Login)
      - JWT im Authorization Header (Bearer Token)
    """
    return UserOut(id=user.id, email=user.email)
