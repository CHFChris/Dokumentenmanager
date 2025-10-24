# app/services/auth_service.py
from __future__ import annotations
from datetime import timedelta
from typing import Dict
from sqlalchemy.orm import Session

from app.repositories.user_repo import (
    get_by_email, get_by_username, get_by_identifier, create_user
)
from app.core.security import hash_password, verify_password, jwt_service  # <- HIER!
from app.core.config import settings


def register_user(db: Session, *, username: str, email: str, password: str) -> Dict:
    if get_by_email(db, email):
        raise ValueError("EMAIL_EXISTS")
    if get_by_username(db, username):
        raise ValueError("USERNAME_EXISTS")
    pwd_hash = hash_password(password)
    user = create_user(db, username=username, email=email, password_hash=pwd_hash, role_id=1)
    return {"id": user.id, "username": user.username, "email": user.email}


def verify_login(db: Session, *, identifier: str, password: str) -> bool:
    user = get_by_identifier(db, identifier)
    return bool(user and verify_password(password, user.password_hash))


def login_user(db: Session, *, identifier: str, password: str) -> Dict:
    user = get_by_identifier(db, identifier)
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("INVALID_CREDENTIALS")

    minutes = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    token = jwt_service.create_token(
        subject=user.id,
        expires_delta=timedelta(minutes=minutes),
        claims={"username": user.username, "email": user.email, "role_id": user.role_id},
    )
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role_id": user.role_id,
        },
    }
