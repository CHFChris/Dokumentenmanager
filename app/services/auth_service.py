from sqlalchemy.orm import Session
from passlib.hash import bcrypt
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
        # hier bewusst eine Exception werfen – dein Router wandelt das in 409 o.ä. um
        raise ValueError("USER_EXISTS")

    pwd_hash = bcrypt.hash(password)
    user = create_user(db, email, pwd_hash)  # legt ggf. auch Quota an (wenn du das so implementiert hast)
    return {"id": user.id, "email": user.email}

def verify_login(db: Session, email: str, password: str):
    user = get_by_email(db, email)
    if not user:
        return None
    if not bcrypt.verify(password, user.password_hash):
        return None
    return user

def login_user(db: Session, email: str, password: str) -> dict:
    """
    Prüft Credentials und liefert {token, user:{id,email}} zurück,
    damit dein Frontend direkt weiterarbeiten kann.
    """
    user = verify_login(db, email, password)
    if not user:
        # wird im Router in 401 übersetzt
        raise ValueError("INVALID_CREDENTIALS")

    token = _create_access_token(user.id)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email}
    }
