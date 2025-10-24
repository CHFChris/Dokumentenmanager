# app/api/deps.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.security import jwt_service
from app.db.database import get_db
from app.repositories.user_repo import get_by_id

# ----------------------------------------------------------
# Security
# ----------------------------------------------------------
security = HTTPBearer(auto_error=False)

@dataclass
class CurrentUser:
    id: int
    username: str
    email: str
    role_id: int
    display_name: Optional[str] = None


# ----------------------------------------------------------
# Helper
# ----------------------------------------------------------
def _user_from_payload(db: Session, payload: dict) -> CurrentUser:
    user_id = int(payload.get("sub", 0) or 0)
    user = get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return CurrentUser(
        id=user.id,
        username=user.username,
        email=user.email,
        role_id=user.role_id,
        display_name=getattr(user, "display_name", None),
    )


def _decode_or_401(token: str, db: Session) -> CurrentUser:
    try:
        payload = jwt_service.decode_token(token)
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    return _user_from_payload(db, payload)


# ----------------------------------------------------------
# Cookie-basierte Authentifizierung (Web)
# ----------------------------------------------------------
def get_current_user_web(
    request: Request,
    db: Session = Depends(get_db)
) -> CurrentUser:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _decode_or_401(token, db)


# ----------------------------------------------------------
# Bearer-Token-Authentifizierung (API)
# ----------------------------------------------------------
def get_current_user_api(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _decode_or_401(credentials.credentials, db)


# ----------------------------------------------------------
# Flexibel: erst Bearer prüfen, sonst Cookie
# ----------------------------------------------------------
def get_current_user_any(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials and credentials.scheme.lower() == "bearer":
        return _decode_or_401(credentials.credentials, db)
    token = request.cookies.get("access_token")
    if token:
        return _decode_or_401(token, db)
    raise HTTPException(status_code=401, detail="Not authenticated")


# ----------------------------------------------------------
# Legacy-Alias für alte Routen
# ----------------------------------------------------------
def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> CurrentUser:
    return get_current_user_web(request, db)
