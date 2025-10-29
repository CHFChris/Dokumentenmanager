# app/services/auth_service.py
from __future__ import annotations

from datetime import timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session
from passlib.hash import bcrypt_sha256

from app.repositories.user_repo import (
    get_by_email,
    get_by_username,
    get_by_identifier,
    create_user,
)
from app.core.security import hash_password, verify_password, jwt_service
from app.core.config import settings
from app.services.email_verification_service import send_verification_email
from app.core.password_policy import validate_password, PasswordPolicyError


def register_user(db: Session, *, username: str, email: str, password: str) -> Dict:
    # Deduplizieren
    if get_by_email(db, email):
        raise ValueError("EMAIL_EXISTS")
    if get_by_username(db, username):
        raise ValueError("USERNAME_EXISTS")

    # Passwort-Policy
    try:
        validate_password(password)
    except PasswordPolicyError:
        raise ValueError("WEAK_PASSWORD")

    # Anlegen
    pwd_hash = hash_password(password)
    user = create_user(db, username=username, email=email, password_hash=pwd_hash, role_id=1)

    # Verifizierungs-Mail senden (Fehler sollen die Registrierung nicht blockieren)
    email_sent = True
    try:
        send_verification_email(db, user, ttl_hours=24)
    except Exception:
        email_sent = False

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "email_sent": email_sent,
    }


def verify_login(db: Session, identifier: str, password: str):
    user = get_by_identifier(db, identifier)
    if not user:
        return None

    # Hauptprüfung
    ok = verify_password(password, user.password_hash)
    if not ok:
        # Fallback fuer Alt-Hashes
        try:
            ok = bcrypt_sha256.verify(password, user.password_hash)
        except Exception:
            ok = False
    if not ok:
        return None

    if not getattr(user, "is_verified", False):
        return "NOT_VERIFIED"

    return user


def login_user(db: Session, identifier: str, password: str) -> Optional[Dict]:
    res = verify_login(db, identifier=identifier, password=password)
    if res is None or res == "NOT_VERIFIED":
        return res

    user = res
    minutes = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    token = jwt_service.create_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=minutes),
        claims={
            "username": user.username,
            "email": user.email,
            "role_id": user.role_id,
        },
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
