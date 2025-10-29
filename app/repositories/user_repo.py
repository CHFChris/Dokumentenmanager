# app/repositories/user_repo.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import exists

from app.models.user import User


# ------------------------------------------------------------
# READ
# ------------------------------------------------------------
def get_by_id(db: Session, user_id: int) -> Optional[User]:
    obj = db.get(User, user_id)
    if obj is not None:
        return obj
    return db.scalar(select(User).where(User.id == user_id))


def get_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email))


def get_by_username(db: Session, username: str) -> Optional[User]:
    return db.scalar(select(User).where(User.username == username))


def get_by_identifier(db: Session, identifier: str) -> Optional[User]:
    u = db.scalar(select(User).where(User.username == identifier))
    if u:
        return u
    return db.scalar(select(User).where(User.email == identifier))


def is_username_available(db: Session, username: str) -> bool:
    return not db.scalar(select(exists().where(User.username == username)))


def is_email_available(db: Session, email: str) -> bool:
    return not db.scalar(select(exists().where(User.email == email)))


# ------------------------------------------------------------
# CREATE
# ------------------------------------------------------------
def create_user(
    db: Session,
    *,
    username: str,
    email: str,
    password_hash: str,
    role_id: int = 1,
) -> User:
    user = User(username=username, email=email, password_hash=password_hash, role_id=role_id)
    db.add(user)
    try:
        db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(user)
    return user


# ------------------------------------------------------------
# UPDATE
# ------------------------------------------------------------
def update_password_hash(db: Session, user_id: int, new_hash: str) -> None:
    user = db.get(User, user_id)
    if not user:
        return
    user.password_hash = new_hash
    db.commit()


def update_password_hash_and_changed_at(db: Session, user_id: int, pwd_hash: str, changed_at: datetime) -> None:
    """
    UPDATE users
       SET password_hash = :pwd_hash,
           password_changed_at = :changed_at
     WHERE id = :user_id
    """
    user = db.get(User, user_id)
    if not user:
        return
    user.password_hash = pwd_hash
    user.password_changed_at = changed_at
    db.commit()


def update_email(db: Session, user_id: int, new_email: str) -> None:
    user = db.get(User, user_id)
    if not user:
        return
    user.email = new_email
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise


def update_username(db: Session, user_id: int, new_username: str) -> None:
    user = db.get(User, user_id)
    if not user:
        return
    user.username = new_username
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise


def update_display_name(db: Session, user_id: int, display_name: Optional[str]) -> None:
    user = db.get(User, user_id)
    if not user:
        return
    user.display_name = display_name
    db.commit()


def set_role(db: Session, user_id: int, role_id: int) -> None:
    user = db.get(User, user_id)
    if not user:
        return
    user.role_id = role_id
    db.commit()


def mark_user_verified(db: Session, user_id: int) -> bool:
    """
    Setzt is_verified = True und setzt den Verifizierungszeitpunkt in UTC.
    Idempotent: Wenn der User schon verifiziert ist, passiert nichts.
    Unterstützt sowohl 'email_verified_at' als auch 'verified_at'.
    Returns:
        True, wenn erfolgreich (auch bei bereits verifiziert)
        False, wenn User nicht existiert
    """
    user = db.get(User, user_id)
    if not user:
        return False

    if getattr(user, "is_verified", False):
        return True

    now = datetime.now(timezone.utc)
    user.is_verified = True

    # bevorzugt explizite Spalte, fällt auf alternative zurück
    if hasattr(user, "email_verified_at"):
        user.email_verified_at = now
    elif hasattr(user, "verified_at"):
        user.verified_at = now

    db.add(user)
    db.commit()
    return True
