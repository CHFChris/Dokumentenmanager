# app/api/deps.py
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.repositories.user_repo import get_by_id
import jwt
from app.core.config import settings

class CurrentUser:
    def __init__(self, id: int, email: str):
        self.id = id
        self.email = email

def _user_from_token(db: Session, token: str) -> CurrentUser:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "Invalid token"})
    user = get_by_id(db, uid)
    if not user:
        raise HTTPException(status_code=401, detail={"code": "NO_USER", "message": "User not found"})
    return CurrentUser(id=user.id, email=user.email)

def get_current_user_web(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail={"code": "NO_AUTH", "message": "Login required"})
    return _user_from_token(db, token)
