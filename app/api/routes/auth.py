# app/api/routes/auth.py
from __future__ import annotations
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

# Kein Prefix hier; main.py setzt z. B. prefix="/auth"
router = APIRouter(tags=["auth"])

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ======================
# API: JSON Endpunkte
# ======================

@router.post("/register", response_model=UserOut, status_code=201, openapi_extra={"security": []})
def api_register(body: RegisterIn, db: Session = Depends(get_db)):
    try:
        data = register_user(db, username=body.username, email=body.email, password=body.password)
        return data
    except ValueError as ex:
        msg = str(ex)
        if msg == "EMAIL_EXISTS":
            raise HTTPException(status_code=409, detail="EMAIL_EXISTS")
        if msg == "USERNAME_EXISTS":
            raise HTTPException(status_code=409, detail="USERNAME_EXISTS")
        raise

@router.post("/login", openapi_extra={"security": []})
def api_login(body: LoginIn, db: Session = Depends(get_db)):
    try:
        return login_user(db, identifier=body.identifier, password=body.password)
    except ValueError as ex:
        if str(ex) == "INVALID_CREDENTIALS":
            raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")
        raise

@router.post("/logout", status_code=204)
def api_logout(response: Response):
    response.delete_cookie("access_token")
    return Response(status_code=204)

# --- JSON: Passwort-Reset Start (mit 404/429)
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
    identifier: str = Form(...),  # E-Mail ODER Benutzername
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    # Vorprüfung für UX (Fehlerhinweis/„Passwort vergessen?“)
    user_ok = verify_login(db, identifier=identifier, password=password)
    if not user_ok:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "error": "E-Mail/Benutzername oder Passwort falsch.",
                "bad_login": True,
            },
            status_code=401,
        )

    data = login_user(db, identifier=identifier, password=password)
    redirect_to = request.query_params.get("next") or "/dashboard"
    resp = RedirectResponse(url=redirect_to, status_code=303)
    resp.set_cookie(
        key="access_token",
        value=data["token"],
        httponly=True,
        samesite="lax",
        path="/",
        # TODO(PROD): secure=True setzen
    )
    return resp

# --- Backup-Variante
@router.post("/login-web-safe", openapi_extra={"security": []})
def login_submit_safe(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        result = login_user(db, identifier=identifier, password=password)
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
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        _ = register_user(db, username=username, email=email, password=password)
    except ValueError as ex:
        msg = str(ex)
        if msg == "EMAIL_EXISTS":
            err = "E-Mail bereits vergeben."
        elif msg == "USERNAME_EXISTS":
            err = "Benutzername bereits vergeben."
        else:
            err = "Registrierung fehlgeschlagen."
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "user": None, "error": err},
            status_code=400,
        )

    # direkt einloggen (per Benutzername)
    data = login_user(db, identifier=username, password=password)
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(
        key="access_token",
        value=data["token"],
        httponly=True,
        samesite="lax",
        path="/",
        # TODO(PROD): secure=True setzen
    )
    return resp

@router.post("/logout-web", openapi_extra={"security": []})
def logout_web():
    resp = RedirectResponse(url="/auth/login-web", status_code=303)
    resp.delete_cookie("access_token")
    return resp

# --- Passwort-Reset (HTML)
@router.get("/password-reset", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_request_form(request: Request):
    return templates.TemplateResponse(
        "password_reset_request.html",
        {"request": request, "sent": False},
    )

@router.post("/password-reset", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_request_submit(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    start_password_reset(db, email)  # kein Enumeration-Leak
    return templates.TemplateResponse(
        "password_reset_request.html",
        {"request": request, "sent": True},
    )

@router.post("/password-reset/start-web", openapi_extra={"security": []})
def password_reset_start_web(email: str = Form(...), db: Session = Depends(get_db)):
    result = start_password_reset(db, email)
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Diese E-Mail ist nicht registriert.")
    if result == "RATE_LIMIT":
        raise HTTPException(status_code=429, detail="Bitte erneut in 10 Minuten versuchen.")
    return {"status": "ok"}

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
            "error": "Token ungültig/abgelaufen oder Passwort-Policy verletzt.",
        },
        status_code=400,
    )
