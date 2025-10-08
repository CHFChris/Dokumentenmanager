from fastapi import Depends, Header
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.security import jwt_service
from app.core.errors import unauthorized

class CurrentUser:
    def __init__(self, user_id: int, email: str):
        self.id = user_id
        self.email = email

def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        unauthorized("Missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt_service.decode_token(token)
        return CurrentUser(user_id=int(payload["sub"]), email=payload.get("email", ""))
    except Exception:
        unauthorized("Invalid or expired token")

DbDep = get_db
