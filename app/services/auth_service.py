from sqlalchemy.orm import Session
from passlib.hash import argon2
from datetime import datetime, timedelta, timezone
import jwt  # PyJWT

from app.repositories.user_repo import get_by_email, create_user
from app.core.config import settings

ALGORITHM = "HS256"

def _create_access_token(user_id: int) -> str:
    expire_minutes = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)

def register_user(db: Session, email: str, password: str) -> dict:
    # existiert E-Mail bereits?
    if get_by_email(db, email):
        raise ValueError("USER_EXISTS")

    # richtig:
    pwd_hash = argon2.hash(password)

    user = create_user(db, email, pwd_hash)
    return {"id": user.id, "email": user.email}

def verify_login(db: Session, email: str, password: str):
    user = get_by_email(db, email)
    if not user:
        return None
    # diese Zeile gehört IN die Funktion und nutzt bcrypt_sha256
    if not argon2.verify(password, user.password_hash):
        return None
    return user

def login_user(db: Session, email: str, password: str) -> dict:
    user = verify_login(db, email, password)
    if not user:
        raise ValueError("INVALID_CREDENTIALS")

    token = _create_access_token(user.id)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email}
    }
