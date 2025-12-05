# app/api/routes/profile.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_web, CurrentUser
from app.core.security import verify_password, get_password_hash
from app.db.database import get_db
from app.web.templates import templates
from app.models.user import User

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
            "delete_error": None,
            "delete_success": None,
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
                "delete_error": None,
                "delete_success": None,
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
                "delete_error": None,
                "delete_success": None,
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
                "delete_error": None,
                "delete_success": None,
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
            "delete_error": None,
            "delete_success": None,
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
    request: Request,
    current_password_delete: str = Form(...),
    confirm_delete: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    # 1) Echten DB-User holen
    db_user: User | None = (
        db.query(User)
        .filter(User.id == current_user.id)
        .first()
    )

    if not db_user:
        # Fallback: User existiert nicht mehr → zurück zum Login
        return RedirectResponse(url="/auth/login-web", status_code=303)

    # 2) Checkbox prüfen
    if not confirm_delete:
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": db_user,
                "pw_error": None,
                "pw_success": None,
                "delete_error": "Bitte bestätigen Sie die Löschung mit der Checkbox.",
                "delete_success": None,
            },
            status_code=400,
        )

    # 3) Passwort prüfen
    if not verify_password(current_password_delete, db_user.password_hash):
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": db_user,
                "pw_error": None,
                "pw_success": None,
                "delete_error": "Aktuelles Passwort ist falsch.",
                "delete_success": None,
            },
            status_code=400,
        )

    # 4) Benutzer wirklich löschen
    db.delete(db_user)
    db.commit()

    # 5) Cookie invalidieren + Redirect auf Registrierung mit Erfolgsinfo
    resp = RedirectResponse(
        url="/auth/register-web?deleted=1",
        status_code=303,
    )
    resp.delete_cookie("access_token")  # ggf. Cookie-Namen anpassen

    return resp
