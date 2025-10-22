# app/repositories/user_repo.py

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from app.models.user import User


# ------------------------------------------------------------
# 📥 GET / SELECT
# ------------------------------------------------------------

def get_by_id(db: Session, user_id: int) -> Optional[User]:
    """
    Gibt den User anhand der ID zurück.
    Nutzt db.get (SQLAlchemy 2.x), fallback auf select bei speziellen Binds.
    """
    obj = db.get(User, user_id)
    if obj is not None:
        return obj
    return db.scalar(select(User).where(User.id == user_id))


def get_by_email(db: Session, email: str) -> Optional[User]:
    """
    Gibt den User anhand der E-Mail zurück.
    """
    return db.scalar(select(User).where(User.email == email))


# ------------------------------------------------------------
# 📝 CREATE / INSERT
# ------------------------------------------------------------

def create_user(db: Session, email: str, password_hash: str) -> User:
    """
    Legt einen neuen User mit Standardrolle an.
    """
    user = User(email=email, password_hash=password_hash, role_id=1)
    db.add(user)
    db.flush()          # user.id verfügbar, bevor commit
    # Optional: db.execute(insert(Quota).values(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user


# ------------------------------------------------------------
# 🔐 UPDATE / PATCH
# ------------------------------------------------------------

def update_password_hash(db: Session, user_id: int, new_hash: str) -> None:
    """
    Aktualisiert den Passwort-Hash eines Users.
    """
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(password_hash=new_hash)
    )
    db.commit()
