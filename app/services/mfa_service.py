# app/services/mfa_service.py
from __future__ import annotations

import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy.orm import Session

from app.models.mfa_code import MFACode


def _utcnow() -> datetime:
    return datetime.utcnow()


def _ttl_minutes() -> int:
    try:
        return int(os.getenv("MFA_CODE_TTL_MINUTES", "10") or "10")
    except ValueError:
        return 10


def _generate_code_6_digits() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _send_email_smtp(to_email: str, subject: str, body_text: str) -> None:
    host = os.getenv("MAIL_SERVER", "").strip()
    port_raw = os.getenv("MAIL_PORT", "587").strip()
    use_tls_raw = os.getenv("MAIL_USE_TLS", "true").strip().lower()

    user = os.getenv("MAIL_USERNAME", "").strip()
    password = os.getenv("MAIL_PASSWORD", "").strip()

    mail_from = os.getenv("MAIL_FROM", "").strip()
    mail_from_name = os.getenv("MAIL_FROM_NAME", "").strip()

    try:
        port = int(port_raw or "587")
    except ValueError:
        port = 587

    use_tls = use_tls_raw in ("1", "true", "yes")

    if not host or not mail_from:
        raise RuntimeError("MAIL_SERVER/MAIL_FROM fehlt in .env")

    from_header = f"{mail_from_name} <{mail_from}>" if mail_from_name else mail_from

    msg = MIMEText(body_text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_header
    msg["To"] = to_email

    with smtplib.SMTP(host, port, timeout=20) as server:
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if user and password:
            server.login(user, password)
        server.sendmail(mail_from, [to_email], msg.as_string())


def _invalidate_old(db: Session, user_id: int, purpose: str) -> None:
    db.query(MFACode).filter(
        MFACode.user_id == user_id,
        MFACode.purpose == purpose,
        MFACode.used == False,  # noqa: E712
    ).update({"used": True})


def create_and_send_login_code(
    db: Session,
    user_id: int,
    user_email: str,
    ip: Optional[str],
    user_agent: Optional[str],
) -> MFACode:
    code = _generate_code_6_digits()
    expires_at = _utcnow() + timedelta(minutes=_ttl_minutes())

    _invalidate_old(db, user_id, "login")

    row = MFACode(
        user_id=user_id,
        code=code,
        purpose="login",
        expires_at=expires_at,
        used=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    subject = "Dokumentenmanager: Einmalcode fuer Login"
    body = (
        "Ein Login wurde angefordert.\n\n"
        f"Einmalcode: {code}\n"
        f"Gueltig bis (UTC): {expires_at}\n\n"
        f"IP: {ip or '-'}\n"
        f"User-Agent: {user_agent or '-'}\n"
    )

    _send_email_smtp(user_email, subject, body)
    return row


def create_and_send_enable_code(db: Session, user_id: int, user_email: str) -> MFACode:
    code = _generate_code_6_digits()
    expires_at = _utcnow() + timedelta(minutes=_ttl_minutes())

    _invalidate_old(db, user_id, "enable")

    row = MFACode(
        user_id=user_id,
        code=code,
        purpose="enable",
        expires_at=expires_at,
        used=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    subject = "Dokumentenmanager: Code zur 2FA-Aktivierung"
    body = (
        "2FA-Aktivierung wurde angefordert.\n\n"
        f"Aktivierungscode: {code}\n"
        f"Gueltig bis (UTC): {expires_at}\n"
    )

    _send_email_smtp(user_email, subject, body)
    return row


def verify_code(db: Session, user_id: int, challenge_id: str, purpose: str, code_input: str) -> bool:
    row = (
        db.query(MFACode)
        .filter(
            MFACode.id == challenge_id,
            MFACode.user_id == user_id,
            MFACode.purpose == purpose,
        )
        .first()
    )

    if not row:
        return False
    if row.used:
        return False
    if row.expires_at <= _utcnow():
        return False

    if not secrets.compare_digest((row.code or "").strip(), (code_input or "").strip()):
        return False

    row.used = True
    db.add(row)
    db.commit()
    return True
