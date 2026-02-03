from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def _get_user_or_none(db: Session, *, user_id: int) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def set_dashboard_protected_view(
    db: Session,
    *,
    user_id: int,
    enabled: bool,
) -> User:
    user = _get_user_or_none(db, user_id=user_id)
    if user is None:
        raise ValueError("USER_NOT_FOUND")

    user.dashboard_protected_view = bool(enabled)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def toggle_dashboard_protected_view(
    db: Session,
    *,
    user_id: int,
) -> User:
    user = _get_user_or_none(db, user_id=user_id)
    if user is None:
        raise ValueError("USER_NOT_FOUND")

    user.dashboard_protected_view = not bool(user.dashboard_protected_view)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
