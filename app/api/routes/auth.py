# app/api/routes/auth.py
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.auth import RegisterIn, LoginIn, UserOut
from app.services.auth_service import register_user, login_user, verify_login
from app.services.password_reset_service import start_password_reset, complete_password_reset

# Kein Prefix hier, main.py setzt z. B. prefix="/auth"
router = APIRouter(tags=["auth"])

# Template-Pfad
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ======================
# API: JSON Endpunkte
# ======================

@router.post("/register", response_model=UserOut, status_code=201, openapi_extra={"security": []})
def api_register(body: RegisterIn, db: Session = Depends(get_db)):
    try:
        user = register_user(db, body.email, body.password)
        return user
    except ValueError as ex:
        if str(ex) == "USER_EXISTS":
            raise HTTPException(status_code=409, detail="USER_EXISTS")
        raise

@router.post("/login", openapi_extra={"security": []})
def api_login(body: LoginIn, db: Session = Depends(get_db)):
    return login_user(db, body.email, body.password)

@router.post("/logout", status_code=204)
def api_logout(response: Response):
    response.delete_cookie("access_token")
    return Response(status_code=204)


# --- JSON: Passwort-Reset Start (mit 404/429 wie gewünscht)
class PasswordResetStartIn(BaseModel):
    email: EmailStr

@router.post("/password-reset/start", openapi_extra={"security": []})
def password_reset_start(body: PasswordResetStartIn, db: Session = Depends(get_db)):
    result = start_password_reset(db, body.email)
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Email not found")
    if result == "RATE_LIMIT":
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
    return {"status": "ok"}


# ======================
# WEB: HTML-Formulare
# ======================

# --- Login Form
@router.get("/login-web", response_class=HTMLResponse, openapi_extra={"security": []})
def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "user": None, "error": None, "bad_login": False},
    )

@router.post("/login-web", openapi_extra={"security": []})
def login_submit(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    # Login validieren, um ggf. „Passwort vergessen?“ anzeigen zu können
    user_ok = verify_login(db, email, password)
    if not user_ok:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "error": "E-Mail oder Passwort falsch.",
                "bad_login": True,
            },
            status_code=401,
        )

    # Token setzen
    data = login_user(db, email, password)
    redirect_to = request.query_params.get("next") or "/dashboard"
    resp = RedirectResponse(url=redirect_to, status_code=303)
    resp.set_cookie(
        key="access_token",
        value=data["token"],
        httponly=True,
        samesite="lax",
        path="/",
        # secure=True in PROD aktivieren
    )
    return resp

# --- Login alternative Variante (Fallback / Fehlerbehandlung kompakt)
@router.post("/login-web-safe", openapi_extra={"security": []})
def login_submit_safe(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    try:
        result = login_user(db, email, password)
        resp = RedirectResponse(url="/dashboard", status_code=303)
        resp.set_cookie("access_token", result["token"], httponly=True, samesite="lax", secure=False)
        return resp
    except Exception:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Login fehlgeschlagen", "bad_login": True},
            status_code=400
        )


# --- Register Form
@router.get("/register-web", response_class=HTMLResponse, openapi_extra={"security": []})
def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "user": None, "error": None},
    )

@router.post("/register-web", openapi_extra={"security": []})
def register_submit(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        _ = register_user(db, email, password)
    except ValueError as ex:
        err = "E-Mail bereits vergeben." if str(ex) == "USER_EXISTS" else "Registrierung fehlgeschlagen."
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "user": None, "error": err},
            status_code=400,
        )

    data = login_user(db, email, password)
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(
        key="access_token",
        value=data["token"],
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp

@router.post("/logout-web", openapi_extra={"security": []})
def logout_web():
    resp = RedirectResponse(url="/auth/login-web", status_code=303)
    resp.delete_cookie("access_token")
    return resp


# --- Passwort-Reset Web-Form (Schritt 1)
@router.get("/password-reset", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_request_form(request: Request):
    return templates.TemplateResponse(
        "password_reset_request.html",
        {"request": request, "sent": False},
    )

@router.post("/password-reset", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_request_submit(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    # kein Enumeration-Leak
    start_password_reset(db, email)
    return templates.TemplateResponse(
        "password_reset_request.html",
        {"request": request, "sent": True},
    )

# --- Passwort-Reset Web-Form (Variante mit explizitem Feedback)
@router.post("/password-reset/start-web", openapi_extra={"security": []})
def password_reset_start_web(email: str = Form(...), db: Session = Depends(get_db)):
    result = start_password_reset(db, email)
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Diese E-Mail ist nicht registriert.")
    if result == "RATE_LIMIT":
        raise HTTPException(status_code=429, detail="Bitte erneut in 10 Minuten versuchen.")
    return {"status": "ok"}


# --- Passwort-Reset Schritt 2: Neues Passwort setzen
@router.get("/password-reset/confirm", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_confirm_form(request: Request, token: str):
    return templates.TemplateResponse(
        "password_reset_confirm.html",
        {"request": request, "token": token, "ok": None, "error": None},
    )

@router.post("/password-reset/confirm", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_confirm_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ok = complete_password_reset(db, token, password)
    if ok:
        return RedirectResponse(url="/auth/login-web?reset=ok", status_code=303)

    return templates.TemplateResponse(
        "password_reset_confirm.html",
        {
            "request": request,
            "token": token,
            "ok": False,
            "error": "Token ungültig/abgelaufen oder Passwort zu schwach.",
        },
        status_code=400,
    )
