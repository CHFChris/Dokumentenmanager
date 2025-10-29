# app/repositories/email_verification_repo.py
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from app.models.email_verification_token import EmailVerificationToken
from app.models.user import User

def create_token(db: Session, user_id: int, ttl_hours: int = 24) -> EmailVerificationToken:
    now = datetime.now(timezone.utc)
    t = EmailVerificationToken(
        user_id=user_id,
        token=token_urlsafe(32),
        created_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t

def get_token_with_user(db: Session, token_str: str) -> EmailVerificationToken | None:
    stmt = (
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token == token_str)
        .limit(1)
    )
    tok = db.execute(stmt).scalar_one_or_none()
    if tok:
        # ensure user is loaded if needed
        _ = tok.user
    return tok

def mark_token_used(db: Session, token: EmailVerificationToken) -> None:
    token.used_at = datetime.now(timezone.utc)
    db.add(token)
    db.commit()

def mark_user_verified(db: Session, user: User) -> None:
    user.is_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()

def count_resends_last_hour(db: Session, user_id: int) -> int:
    # nutzt Tabelle email_verification_events
    from sqlalchemy import select
    from app.repositories.verification_events_repo import EmailVerificationEvent
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    stmt = select(func.count()).select_from(EmailVerificationEvent).where(
        EmailVerificationEvent.user_id == user_id,
        EmailVerificationEvent.created_at >= since,
        EmailVerificationEvent.kind.in_(("send","resend"))
    )
    return int(db.execute(stmt).scalar() or 0)
