# app/services/login_security_service.py
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional, Tuple

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.login_device import LoginDevice
from app.models.user import User
from app.utils.email_utils import send_mail


def _get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


def _fingerprint_hash(user_agent: str, ip: str) -> str:
    src = f"{user_agent}|{ip}".encode("utf-8", errors="ignore")
    return hashlib.sha256(src).hexdigest()


def handle_login_device_and_email(
    db: Session,
    *,
    user_id: int,
    request: Request,
) -> Tuple[bool, Optional[str]]:
    """Erkennt neues Gerät und sendet optional eine Sicherheitsmail.

    Rückgabe:
    - is_new_device: True wenn Fingerprint für den User neu war
    - mail_status: None wenn keine Mail gesendet wurde, sonst "sent"|"failed"
    """
    db_user: User | None = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        return False, None

    user_agent = (request.headers.get("user-agent") or "").strip()
    if len(user_agent) > 512:
        user_agent = user_agent[:512]
    ip = _get_client_ip(request)

    fp_hash = _fingerprint_hash(user_agent, ip)
    now = datetime.utcnow()

    existing: LoginDevice | None = (
        db.query(LoginDevice)
        .filter(LoginDevice.user_id == user_id, LoginDevice.fingerprint_hash == fp_hash)
        .first()
    )

    if existing:
        existing.last_seen_at = now
        existing.last_ip = ip
        existing.last_user_agent = user_agent
        db.add(existing)
        db.commit()
        return False, None

    dev = LoginDevice(
        user_id=user_id,
        fingerprint_hash=fp_hash,
        first_seen_at=now,
        last_seen_at=now,
        last_ip=ip,
        last_user_agent=user_agent,
    )
    db.add(dev)
    db.commit()

    if not getattr(db_user, "security_email_new_device_enabled", True):
        return True, None

    subject = "Sicherheits-Hinweis: Neuer Login"
    text = (
        "Es gab einen Login in deinen Account von einem neuen Gerät.\n\n"
        f"Zeit (UTC): {now.isoformat()}\n"
        f"IP: {ip}\n"
        f"User-Agent: {user_agent}\n\n"
        "Wenn du das nicht warst: Passwort ändern und Account prüfen."
    )
    html = (
        "<p>Es gab einen Login in deinen Account von einem <b>neuen Gerät</b>.</p>"
        f"<p><b>Zeit (UTC):</b> {now.isoformat()}<br/>"
        f"<b>IP:</b> {ip}<br/>"
        f"<b>User-Agent:</b> {user_agent}</p>"
        "<p>Wenn du das nicht warst: Passwort ändern und Account prüfen.</p>"
    )

    ok = send_mail(db_user.email, subject, html_body=html, text_body=text)
    return True, ("sent" if ok else "failed")
