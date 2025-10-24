# app/repositories/user_repo.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import exists

from app.models.user import User


# ------------------------------------------------------------
# 📥 READ
# ------------------------------------------------------------
def get_by_id(db: Session, user_id: int) -> Optional[User]:
    """User per Primärschlüssel laden (SQLAlchemy 2.x)."""
    obj = db.get(User, user_id)
    if obj is not None:
        return obj
    return db.scalar(select(User).where(User.id == user_id))

def get_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email))

def get_by_username(db: Session, username: str) -> Optional[User]:
    return db.scalar(select(User).where(User.username == username))

def get_by_identifier(db: Session, identifier: str) -> Optional[User]:
    """
    E-Mail ODER Benutzername zulassen.
    Zuerst Username (häufig kürzer), dann E-Mail.
    """
    u = db.scalar(select(User).where(User.username == identifier))
    if u:
        return u
    return db.scalar(select(User).where(User.email == identifier))

def is_username_available(db: Session, username: str) -> bool:
    """True, wenn Username noch frei ist."""
    return not db.scalar(select(exists().where(User.username == username)))

def is_email_available(db: Session, email: str) -> bool:
    """True, wenn E-Mail noch frei ist."""
    return not db.scalar(select(exists().where(User.email == email)))


# ------------------------------------------------------------
# 📝 CREATE
# ------------------------------------------------------------
def create_user(
    db: Session,
    *,
    username: str,
    email: str,
    password_hash: str,
    role_id: int = 1,
) -> User:
    """
    Neuen User anlegen. Bei Unique-Verstößen: IntegrityError (im Service → 409 mappen).
    """
    user = User(username=username, email=email, password_hash=password_hash, role_id=role_id)
    db.add(user)
    try:
        db.flush()   # ID verfügbar (für Folgeinserts)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(user)
    return user


# ------------------------------------------------------------
# 🔐 UPDATE
# ------------------------------------------------------------
def update_password_hash(db: Session, user_id: int, new_hash: str) -> None:
    user = db.get(User, user_id)
    if not user:
        return
    user.password_hash = new_hash
    db.commit()

def update_email(db: Session, user_id: int, new_email: str) -> None:
    """Unique-Verstoß führt zu IntegrityError (oben abfangen)."""
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
    """Unique-Verstoß führt zu IntegrityError (oben abfangen)."""
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
