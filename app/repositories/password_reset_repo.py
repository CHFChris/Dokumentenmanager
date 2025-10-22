from sqlalchemy.orm import Session
from sqlalchemy import select, update
from datetime import datetime
from typing import Optional
from app.models.password_reset_token import PasswordResetToken

def create_reset_token(db: Session, user_id: int, token_hash: str, expires_at: datetime) -> PasswordResetToken:
    rec = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec

def get_valid_token(db: Session, token_hash: str) -> Optional[PasswordResetToken]:
    stmt = select(PasswordResetToken).where(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > datetime.utcnow()
    ).limit(1)
    return db.scalars(stmt).first()

def mark_used(db: Session, rec: PasswordResetToken):
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.id == rec.id)
        .values(used_at=datetime.utcnow())
    )
    db.commit()
