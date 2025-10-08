from sqlalchemy.orm import Session
from sqlalchemy import select, insert
from app.models.user import User
from app.models.user import Base  # falls benötigt

def get_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    return db.scalar(stmt)

def create_user(db: Session, email: str, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash, role_id=1)
    db.add(user)
    db.flush()         # id befüllt
    # Optional: Quota anlegen, wenn du das Feature gleich nutzen willst
    # db.execute(insert(Quota).values(user_id=user.id)) 
    db.commit()
    db.refresh(user)
    return user
