from __future__ import annotations

from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def create_access_log(
    db: Session,
    *,
    user_id: int | None,
    document_id: int | None,
    action: str,
    success: bool = True,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    log = AuditLog(
        user_id=user_id,
        document_id=document_id,
        action=action,
        success=success,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
