# app/api/routes/account.py
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.services import mfa_service
from app.services.auth_service import verify_login

router = APIRouter(prefix="/account", tags=["account"])


class PasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=255)


class EnableVerifyRequest(BaseModel):
    challenge_id: str
    code: str = Field(..., min_length=4, max_length=16)


def _decode_token_subject(token: str) -> Optional[str]:
    secret = os.getenv("SECRET_KEY", "").strip()
    alg = os.getenv("JWT_ALGORITHM", "HS256").strip()
    if not secret:
        return None

    try:
        from jose import jwt as jose_jwt  # type: ignore
        payload = jose_jwt.decode(token, secret, algorithms=[alg])
        return str(payload.get("sub")) if payload.get("sub") is not None else None
    except Exception:
        try:
            import jwt as pyjwt  # type: ignore
            payload = pyjwt.decode(token, secret, algorithms=[alg])
            return str(payload.get("sub")) if payload.get("sub") is not None else None
        except Exception:
            return None


def _extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()

    return request.cookies.get("access_token")


def _get_current_user(request: Request, db: Session) -> User:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    sub = _decode_token_subject(token)
    if not sub or not sub.isdigit():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.id == int(sub)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
    return user


def _verify_password(db: Session, user: User, plain: str) -> bool:
    identifier = getattr(user, "email", None) or getattr(user, "username", None)
    if not identifier:
        return False

    res = verify_login(db, identifier=str(identifier), password=plain)
    if res is None:
        return False
    return True


@router.post("/mfa/enable/start")
def mfa_enable_start(body: PasswordRequest, request: Request, db: Session = Depends(get_db)):
    user = _get_current_user(request, db)

    if not _verify_password(db, user, body.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    row = mfa_service.create_and_send_enable_code(db, int(user.id), user.email)
    return {"challenge_id": str(row.id)}


@router.post("/mfa/enable/verify")
def mfa_enable_verify(body: EnableVerifyRequest, request: Request, db: Session = Depends(get_db)):
    user = _get_current_user(request, db)

    ok = mfa_service.verify_code(db, int(user.id), body.challenge_id, "enable", body.code)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid code")

    user.mfa_enabled = True
    user.mfa_method = "email"
    db.add(user)
    db.commit()

    return {"mfa_enabled": True, "mfa_method": "email"}


@router.post("/mfa/disable")
def mfa_disable(body: PasswordRequest, request: Request, db: Session = Depends(get_db)):
    user = _get_current_user(request, db)

    if not _verify_password(db, user, body.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    user.mfa_enabled = False
    user.mfa_method = "email"
    db.add(user)
    db.commit()

    return {"mfa_enabled": False}
