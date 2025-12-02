# app/api/routes/profile.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db
from app.web.templates import templates
from app.core.security import verify_password, get_password_hash
from app.models.user import User  # dein User-ORM-Modell

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/")
def profile_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    db_user = db.query(User).filter(User.id == current_user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": db_user,
            "pw_error": None,
            "pw_success": None,
        },
    )


@router.post("/update-basic")
def update_basic_profile(
    name: str = Form(...),
    language: str = Form(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    db_user = db.query(User).filter(User.id == current_user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Name auf display_name mappen (entspricht deinem Modell)
    db_user.display_name = name.strip()
    db_user.language = language.strip()

    db.add(db_user)
    db.commit()

    return RedirectResponse(url="/profile", status_code=303)


@router.post("/change-password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_repeat: str = Form(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    db_user = db.query(User).filter(User.id == current_user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1) Aktuelles Passwort prüfen
    if not verify_password(current_password, db_user.password_hash):
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": db_user,
                "pw_error": "Das aktuelle Passwort ist falsch.",
                "pw_success": None,
            },
            status_code=400,
        )

    # 2) Neue Passwörter vergleichen
    if new_password != new_password_repeat:
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": db_user,
                "pw_error": "Die neuen Passwörter stimmen nicht überein.",
                "pw_success": None,
            },
            status_code=400,
        )

    # 3) Optional: Policy
    if len(new_password) < 8:
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": db_user,
                "pw_error": "Neues Passwort muss mindestens 8 Zeichen lang sein.",
                "pw_success": None,
            },
            status_code=400,
        )

    # 4) Passwort setzen
    db_user.password_hash = get_password_hash(new_password)
    db_user.password_changed_at = datetime.utcnow()

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # 5) Erfolgs-Nachricht
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": db_user,
            "pw_error": None,
            "pw_success": "Passwort wurde erfolgreich geändert.",
        },
    )


@router.post("/change-email")
def change_email(
    current_password: str = Form(...),
    new_email: str = Form(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    db_user = db.query(User).filter(User.id == current_user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(current_password, db_user.password_hash):
        raise HTTPException(status_code=400, detail="Aktuelles Passwort ist falsch")

    db_user.email = new_email.strip().lower()
    db.add(db_user)
    db.commit()

    return RedirectResponse(url="/profile?email_changed=1", status_code=303)


@router.post("/delete-account")
def delete_account(
    current_password: str = Form(...),
    confirm_delete: str = Form(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    """
    confirm_delete: zweite Sicherheitsabfrage, z. B. 'JA'.
    """
    if confirm_delete.strip().upper() != "JA":
        raise HTTPException(status_code=400, detail="Löschung nicht bestätigt")

    db_user = db.query(User).filter(User.id == current_user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(current_password, db_user.password_hash):
        raise HTTPException(status_code=400, detail="Aktuelles Passwort ist falsch")

    db.delete(db_user)
    db.commit()

    # Nach dem Löschen zur Logout-/Login-Route
    return RedirectResponse(url="/auth/logout-web", status_code=303)
