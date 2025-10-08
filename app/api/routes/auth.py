from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.auth import RegisterIn, LoginIn, TokenOut  # falls so benannt
from app.services.auth_service import register_user, login_user
from app.db.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    try:
        return register_user(db, body.email, body.password)
    except ValueError as ex:
        if str(ex) == "USER_EXISTS":
            raise HTTPException(status_code=409, detail={"code": "USER_EXISTS", "message": "Email already registered"})
        raise

@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    try:
        data = login_user(db, body.email, body.password)
        # TokenOut erwartet vermutlich {token:str, user:{id:int,email:str}}
        return data
    except ValueError as ex:
        if str(ex) == "INVALID_CREDENTIALS":
            raise HTTPException(status_code=401, detail={"code":"INVALID_CREDENTIALS","message":"Email oder Passwort falsch"})
        raise
