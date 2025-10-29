# app/services/password_reset_service.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_token, hash_password
from app.models.password_reset_token import PasswordResetToken
from app.repositories.user_repo import (
    get_by_email,
    get_by_id,
    update_password_hash_and_changed_at,
)
from app.repositories.password_reset_repo import (
    create_reset_token,   # (db, user_id: int, token_hash: str, expires_at: datetime)
    get_valid_token,      # (db, token_hash: str) -> PasswordResetToken | None
    mark_used,            # (db, token: PasswordResetToken) -> None
    # optional: invalidate_other_tokens(db, user_id: int, except_token_id: int)
)
from app.utils.email_utils import send_mail
from app.core.password_policy import validate_password, PasswordPolicyError


# --------------- Config ---------------
RATE_LIMIT_MINUTES: int = getattr(settings, "RESET_RATE_LIMIT_MINUTES", 10)
TOKEN_EXPIRE_MINUTES: int = getattr(settings, "RESET_TOKEN_EXPIRE_MINUTES", 60)
PUBLIC_BASE_URL: str = getattr(settings, "PUBLIC_BASE_URL", "http://127.0.0.1:8000")

StartStatus = Literal["OK", "NOT_FOUND", "RATE_LIMIT"]


# --------------- Helpers ---------------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def too_many_recent_requests(db: Session, user_id: int, minutes: int = RATE_LIMIT_MINUTES) -> bool:
    """Rate-Limit: true, wenn in den letzten 'minutes' bereits ein Reset-Token erzeugt wurde."""
    if minutes <= 0:
        return False
    since = _now_utc() - timedelta(minutes=minutes)
    stmt = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.created_at >= since,
    )
    return db.scalars(stmt).first() is not None


# --------------- Public API ---------------
def start_password_reset(db: Session, email: str) -> StartStatus:
    """
    Erzeugt einen neuen Reset-Token (Hash wird gespeichert) und sendet eine E-Mail.
    Rueckgabe:
      - "OK"          : E-Mail versendet
      - "NOT_FOUND"   : kein User mit E-Mail
      - "RATE_LIMIT"  : zu viele Anfragen in kurzer Zeit
    """
    user = get_by_email(db, email)
    if not user:
        return "NOT_FOUND"

    if too_many_recent_requests(db, user.id, RATE_LIMIT_MINUTES):
        return "RATE_LIMIT"

    import secrets
    raw_token = secrets.token_urlsafe(32)
    token_hash_value = hash_token(raw_token)

    expires_at = _now_utc() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    create_reset_token(db, user.id, token_hash_value, expires_at)

    link = f"{PUBLIC_BASE_URL}/auth/password-reset/confirm?token={raw_token}"

    subject = "Passwort zuruecksetzen"
    text_body = (
        f"Hallo {user.email},\n\n"
        f"du hast eine Anfrage zum Zuruecksetzen deines Passworts gestellt.\n"
        f"Link (gueltig {TOKEN_EXPIRE_MINUTES} Minuten):\n\n{link}\n\n"
        f"Wenn du das nicht warst, ignoriere diese E-Mail."
    )
    html_body = (
        f"<p>Hallo <b>{user.email}</b>,</p>"
        f"<p>du hast eine Anfrage zum Zuruecksetzen deines Passworts gestellt.</p>"
        f'<p><a href="{link}" target="_blank">Hier klicken, um ein neues Passwort zu setzen</a></p>'
        f"<p>Der Link ist {TOKEN_EXPIRE_MINUTES} Minuten gueltig.</p>"
        f"<p>Wenn du das nicht warst, ignoriere diese E-Mail.</p>"
    )

    send_mail(user.email, subject, html_body, text_body)
    return "OK"


def complete_password_reset(db: Session, raw_token: str, new_password: str) -> bool:
    """
    Validiert den Reset-Token (per Hash) und setzt ein neues Passwort,
    wenn die Passwort-Policy erfuellt ist. Rueckgabe True bei Erfolg, sonst False.
    """
    try:
        # Policy pruefen (fruehzeitig)
        try:
            validate_password(new_password)
        except PasswordPolicyError:
            return False

        # Token gegen Hash validieren
        token_hash_value = hash_token(raw_token)
        rec = get_valid_token(db, token_hash_value)
        if not rec:
            return False

        user = get_by_id(db, rec.user_id)
        if not user:
            return False

        # Passwort setzen
        pwd_hash = hash_password(new_password)
        changed_at = _now_utc()
        update_password_hash_and_changed_at(db, user.id, pwd_hash, changed_at)

        # Token verbrauchen
        mark_used(db, rec)

        # Optional: weitere Tokens invalidieren (falls Repo-Funktion vorhanden)
        # invalidate_other_tokens(db, user.id, except_token_id=rec.id)

        return True
    except Exception:
        return False
