# app/repositories/user_repo.py
from sqlalchemy.orm import Session
from sqlalchemy import select, insert
from typing import Optional

from app.models.user import User  # passt zu deinem Model-Pfad

def get_by_id(db: Session, user_id: int) -> Optional[User]:
    # schnellster Weg: db.get (SQLAlchemy 2.x)
    obj = db.get(User, user_id)
    if obj is not None:
        return obj
    # Fallback (falls db.get nicht greift, z. B. bei speziellen Binds)
    return db.scalar(select(User).where(User.id == user_id))

def get_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email))

def create_user(db: Session, email: str, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash, role_id=1)
    db.add(user)
    db.flush()          # user.id verfügbar
    # Optional: Quota-Row anlegen, wenn deine DB das vorsieht:
    # db.execute(insert(Quota).values(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user
