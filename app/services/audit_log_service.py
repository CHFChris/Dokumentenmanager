from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def log_event_safe(
    db: Session,
    *,
    actor_user_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    outcome: str = "success",
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    details_text: Optional[str] = None,
) -> None:
    try:
        row = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            ip=ip,
            user_agent=user_agent,
            details_text=details_text,
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("audit log write failed")
        return
