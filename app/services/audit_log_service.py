# app/services/audit_log_service.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from starlette.requests import Request
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.repositories.access_log_repo import create_access_log


logger = logging.getLogger(__name__)

LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAILED = "LOGIN_FAILED"
LOGOUT = "LOGOUT"
PASSWORD_CHANGE = "PASSWORD_CHANGE"
PROFILE_CHANGE = "PROFILE_CHANGE"
ACCOUNT_DELETE = "ACCOUNT_DELETE"
DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD"
DOCUMENT_DELETE = "DOCUMENT_DELETE"
TRASH_RESTORE = "TRASH_RESTORE"


def safe_audit_log(
    db: Session,
    *,
    user_id: Optional[int],
    action: str,
    success: bool,
    document_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Audit-Logging darf Hauptaktion nicht blockieren."""
    try:
        create_access_log(
            db,
            user_id=user_id,
            action=action,
            success=success,
            document_id=document_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except Exception as exc:
        print(f"[AUDIT-LOG-ERROR] {exc!r}")


def try_audit_log(
    *,
    action_type: str,
    success: bool,
    user_id: int | None = None,
    actor_email: str | None = None,
    document_id: int | None = None,
    request: Request | None = None,
    details: str | None = None,
) -> None:
    """Schreibt Audit-Logs ohne die eigentliche Aktion zu blockieren."""
    try:
        ip = None
        ua = None
        if request is not None:
            ip = request.client.host if request.client else None
            ua = request.headers.get("user-agent")

        db = SessionLocal()
        try:
            row = AuditLog(
                created_at=datetime.utcnow(),
                user_id=user_id,
                actor_email=actor_email,
                action_type=(action_type or "")[:64],
                document_id=document_id,
                success=bool(success),
                ip_address=(ip or None),
                user_agent=(ua[:255] if ua else None),
                details=(details or None),
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as ex:
        logger.exception("Audit-Log fehlgeschlagen: %r", ex)
