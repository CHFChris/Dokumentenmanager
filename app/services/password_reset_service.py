# app/services/password_reset_service.py

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_token, hash_password
from app.models.password_reset_token import PasswordResetToken
from app.repositories.user_repo import get_by_email, get_by_id, update_password_hash
from app.repositories.password_reset_repo import create_reset_token, get_valid_token, mark_used
from app.utils.email_utils import send_mail

# Konfigurierbare Werte mit Defaults (über .env / Settings steuerbar)
RATE_LIMIT_MINUTES = getattr(settings, "RESET_RATE_LIMIT_MINUTES", 0)
TOKEN_EXPIRE_MINUTES = getattr(settings, "RESET_TOKEN_EXPIRE_MINUTES", 60)


def too_many_recent_requests(db: Session, user_id: int, minutes: int = RATE_LIMIT_MINUTES) -> bool:
    """
    Max. eine Reset-Mail je Zeitraum: wenn in den letzten `minutes` Minuten
    bereits ein Token erzeugt wurde -> blocken.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    stmt = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.created_at >= since,
    )
    return db.scalars(stmt).first() is not None


def start_password_reset(db: Session, email: str) -> str:
    """
    - Schickt E-Mail nur, wenn User existiert (sonst 'NOT_FOUND').
    - Rate Limit: nur alle RATE_LIMIT_MINUTES erlaubt ('RATE_LIMIT').
    - Bei Erfolg: Token anlegen + Mail versenden ('OK').
    """
    user = get_by_email(db, email)
    if not user:
        return "NOT_FOUND"

    if too_many_recent_requests(db, user.id, RATE_LIMIT_MINUTES):
        return "RATE_LIMIT"

    # neues Roh-Token erzeugen
    import secrets
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)

    # Token per Repository anlegen (nur Hash speichern)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    create_reset_token(db, user.id, token_hash, expires_at)

    # Link bauen (lokal; für Prod ggf. PUBLIC_URL aus settings nutzen)
    link = f"http://127.0.0.1:8000/auth/password-reset/confirm?token={raw_token}"

    # E-Mail senden (SMTP via .env konfiguriert)
    subject = "Passwort zurücksetzen – Dokumentenmanager"
    text_body = f"""
Hallo {user.email},

du hast eine Anfrage zum Zurücksetzen deines Passworts gestellt.
Bitte öffne folgenden Link (gültig {TOKEN_EXPIRE_MINUTES} Minuten):

{link}

Wenn du das nicht warst, ignoriere diese E-Mail.
"""
    html_body = f"""
<p>Hallo <b>{user.email}</b>,</p>
<p>du hast eine Anfrage zum Zurücksetzen deines Passworts gestellt.</p>
<p><a href="{link}" target="_blank" style="color:#2563eb;">Hier klicken, um ein neues Passwort zu setzen</a></p>
<p>Der Link ist {TOKEN_EXPIRE_MINUTES} Minuten gültig.</p>
<p>Wenn du das nicht warst, ignoriere diese E-Mail.</p>
"""

    send_mail(user.email, subject, html_body, text_body)
    return "OK"


def complete_password_reset(db: Session, raw_token: str, new_password: str) -> bool:
    """
    - Prüft Token (Hash, Gültigkeit, nicht benutzt).
    - Validiert Passwortstärke.
    - Aktualisiert das Passwort und markiert Token als benutzt.
    """
    token_hash = hash_token(raw_token)
    rec = get_valid_token(db, token_hash)
    if not rec:
        return False

    if not _is_strong_password(new_password):
        return False

    user = get_by_id(db, rec.user_id)
    if not user:
        return False

    # Einheitlich über Security-Utility hashen
    pwd_hash = hash_password(new_password)
    update_password_hash(db, user.id, pwd_hash)

    mark_used(db, rec)
    return True


def _is_strong_password(pw: str) -> bool:
    """
    Minimalregeln:
    - Länge 8–256
    - mind. 1 Ziffer
    - mind. 1 Buchstabe
    (kann bei Bedarf verschärft werden)
    """
    if not (8 <= len(pw) <= 256):
        return False
    has_digit = any(c.isdigit() for c in pw)
    has_alpha = any(c.isalpha() for c in pw)
    return has_digit and has_alpha
