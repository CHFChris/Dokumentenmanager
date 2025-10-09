# app/api/deps.py
from typing import Optional
from fastapi import Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
import jwt

from app.core.config import settings
from app.db.database import get_db
from app.repositories.user_repo import get_by_id

class CurrentUser:
    def __init__(self, id: int, email: str):
        self.id = id
        self.email = email

def _decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "Invalid token"})

def _load_user(db: Session, user_id: int) -> CurrentUser:
    user = get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail={"code": "NO_USER", "message": "User not found"})
    return CurrentUser(id=user.id, email=user.email)

# === Für API-Calls (Authorization: Bearer <token>) ===
def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"code": "NO_AUTH", "message": "Missing Bearer token"})
    token = authorization.split(" ", 1)[1]
    uid = _decode_token(token)
    return _load_user(db, uid)

# === Für Web (JWT im httpOnly Cookie) ===
def get_current_user_web(
    request: Request,
    db: Session = Depends(get_db),
) -> CurrentUser:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail={"code": "NO_AUTH", "message": "Login required"})
    uid = _decode_token(token)
    return _load_user(db, uid)
