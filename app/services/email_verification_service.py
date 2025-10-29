# app/services/email_verification_service.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email_verification_token import EmailVerificationToken
from app.utils.email_utils import send_mail
from app.repositories.user_repo import get_by_email, get_by_id, mark_user_verified

log = logging.getLogger(__name__)


def _build_verify_url(token: str) -> str:
    base = getattr(settings, "PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/auth/verify/confirm?token={token}"


def _as_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def send_verification_email(db: Session, user, ttl_hours: int = 24) -> bool:
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=ttl_hours)

    db.add(EmailVerificationToken(
        user_id=user.id,
        token=raw,
        created_at=now,
        expires_at=expires,
        used_at=None,
    ))
    db.commit()

    link = _build_verify_url(raw)

    subject = "Bitte bestaetige deine E-Mail-Adresse"
    html = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2 style="color: #2563eb;">Willkommen beim Dokumentenmanager!</h2>
        <p>Hallo {user.email},</p>
        <p>um dein Konto zu aktivieren, bestaetige bitte deine E-Mail-Adresse ueber den folgenden Button:</p>
        <p style="margin: 24px 0;">
            <a href="{link}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                E-Mail bestaetigen
            </a>
        </p>
        <p>Wenn du dich nicht registriert hast, ignoriere diese Nachricht.</p>
        <p>Viele Gruesse,<br><strong>Dokumentenmanager</strong></p>
    </div>
    """.strip()
    text = f"""Willkommen beim Dokumentenmanager!

Hallo {user.email},

um dein Konto zu aktivieren, bestaetige bitte deine E-Mail-Adresse ueber folgenden Link:
{link}

Wenn du dich nicht registriert hast, ignoriere diese Nachricht.

Viele Gruesse
Dokumentenmanager
""".strip()

    try:
        send_mail(user.email, subject, html, text)
        return True
    except Exception as e:
        log.error("Verification email send failed for %s: %s", user.email, e)
        return False


def confirm_verification_token(db: Session, token: str) -> Optional[int]:
    now = datetime.now(timezone.utc)

    if not isinstance(token, str):
        return None
    token = token.strip()
    if not token:
        return None

    try:
        row = db.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.token == token)
        ).scalars().first()
    except Exception as e:
        log.error("DB error selecting token: %s", e)
        return None

    if not row:
        return None

    used_at = _as_aware_utc(row.used_at)
    if used_at is not None:
        return None

    expires_at = _as_aware_utc(row.expires_at)
    if expires_at and expires_at < now:
        return None

    user = get_by_id(db, row.user_id)
    if not user:
        return None

    if not getattr(user, "is_verified", False):
        mark_user_verified(db, user.id)

    row.used_at = now
    db.add(row)
    db.commit()
    return user.id


def confirm_token(db: Session, token: str) -> Optional[int]:
    return confirm_verification_token(db, token)


def resend_verification_email(db: Session, email: str, ttl_hours: int = 24) -> str:
    user = get_by_email(db, email)
    if not user:
        return "NOT_FOUND"
    if getattr(user, "is_verified", False):
        return "ALREADY_VERIFIED"
    ok = send_verification_email(db, user, ttl_hours=ttl_hours)
    return "OK" if ok else "SEND_ERROR"


def is_user_verified(db: Session, email: str) -> bool:
    user = get_by_email(db, email)
    return bool(user and getattr(user, "is_verified", False))


__all__ = [
    "send_verification_email",
    "confirm_verification_token",
    "confirm_token",
    "resend_verification_email",
    "is_user_verified",
]
