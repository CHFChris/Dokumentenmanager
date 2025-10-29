# app/api/routes/auth.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, Response, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.auth import RegisterIn, LoginIn, UserOut

# ---- Option A / B: LoginOut aliasieren ----
try:
    from app.schemas.auth import LoginOut  # type: ignore
except Exception:
    from app.schemas.auth import TokenOut as LoginOut  # type: ignore

from app.services.auth_service import register_user, login_user, verify_login
from app.services.password_reset_service import start_password_reset, complete_password_reset

# Verifizierung
from app.services.email_verification_service import (
    confirm_verification_token,
    resend_verification_email,
    is_user_verified,
)

from app.repositories.user_repo import get_by_email

router = APIRouter(tags=["Auth"])

# Templates-Verzeichnis
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ============================================================
# API: JSON Endpunkte
# ============================================================

@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
    openapi_extra={"security": []},
)
def api_register(body: RegisterIn, db: Session = Depends(get_db)):
    try:
        data = register_user(
            db,
            username=body.username,
            email=body.email,
            password=body.password,
        )
        return data
    except ValueError as ex:
        msg = str(ex)
        if msg == "EMAIL_EXISTS":
            raise HTTPException(status_code=409, detail="EMAIL_EXISTS")
        if msg == "USERNAME_EXISTS":
            raise HTTPException(status_code=409, detail="USERNAME_EXISTS")
        if msg == "WEAK_PASSWORD":
            raise HTTPException(status_code=422, detail="WEAK_PASSWORD")
        raise

@router.post(
    "/login",
    response_model=LoginOut,
    openapi_extra={"security": []},
)
def api_login(body: LoginIn, db: Session = Depends(get_db)):
    res = login_user(db, identifier=body.identifier, password=body.password)
    if res == "NOT_VERIFIED":
        raise HTTPException(status_code=403, detail="Account not verified")
    if res is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return res

@router.post("/logout", status_code=204)
def api_logout(response: Response):
    response.delete_cookie(
        key="access_token",
        path="/",
        samesite="lax",
        secure=False,
        httponly=True,
    )
    return Response(status_code=204)

# ----------------------------
# JSON: Passwort-Reset (Start)
# ----------------------------

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
    identifier: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    pre = verify_login(db, identifier=identifier, password=password)
    if pre is None:
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
    if pre == "NOT_VERIFIED":
        # Leite auf Hinweis-Seite mit Polling
        user = get_by_email(db, identifier) or get_by_email(db, identifier.lower())
        email = user.email if user else identifier
        return RedirectResponse(url=f"/auth/verify/sent?email={email}", status_code=303)

    data = login_user(db, identifier=identifier, password=password)
    redirect_to = request.query_params.get("next") or "/dashboard"
    if not redirect_to.startswith("/"):
        redirect_to = "/dashboard"

    resp = RedirectResponse(url=redirect_to, status_code=303)
    resp.set_cookie(
        key="access_token",
        value=data["token"],
        httponly=True,
        samesite="lax",
        path="/",
        secure=False,  # PROD: True
    )
    return resp

@router.post("/login-web-safe", openapi_extra={"security": []})
def login_submit_safe(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    res = login_user(db, identifier=identifier, password=password)
    if res == "NOT_VERIFIED":
        return RedirectResponse(url=f"/auth/verify/sent?email={identifier}", status_code=303)
    if res is None:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Login fehlgeschlagen", "bad_login": True},
            status_code=401,
        )

    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(
        key="access_token",
        value=res["token"],
        httponly=True,
        samesite="lax",
        path="/",
        secure=False,
    )
    return resp

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
        elif msg == "WEAK_PASSWORD":
            err = "Passwort zu schwach: Mindestens 8 Zeichen, 1 Zahl, 1 Sonderzeichen."
        else:
            err = "Registrierung fehlgeschlagen."
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "user": None, "error": err},
            status_code=400,
        )

    # Kein Auto-Login. Nutzer muss E-Mail verifizieren.
    return RedirectResponse(url=f"/auth/verify/sent?email={email}", status_code=303)

@router.post("/logout-web", openapi_extra={"security": []})
def logout_web():
    resp = RedirectResponse(url="/auth/login-web", status_code=303)
    resp.delete_cookie(
        key="access_token",
        path="/",
        samesite="lax",
        secure=False,
        httponly=True,
    )
    return resp

@router.get("/password-reset", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_request_form(request: Request):
    return templates.TemplateResponse(
        "password_reset_request.html",
        {"request": request, "sent": False},
    )

@router.post("/password-reset", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_request_submit(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    start_password_reset(db, email)
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
            "error": "Token ungueltig/abgelaufen oder Passwort-Policy verletzt.",
        },
        status_code=400,
    )

# ---------- Verifizierung: Seiten & Endpunkte ----------

@router.get("/verify/sent", response_class=HTMLResponse, openapi_extra={"security": []})
def verify_sent(request: Request, email: str = Query(...)):
    return templates.TemplateResponse(
        "verify_sent.html",
        {"request": request, "email": email},
    )

@router.post("/verify/resend", openapi_extra={"security": []})
def verify_resend(email: str = Form(...), db: Session = Depends(get_db)):
    res = resend_verification_email(db, email, ttl_hours=24)
    if res == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Diese E-Mail ist nicht registriert.")
    if res == "ALREADY_VERIFIED":
        return {"status": "already_verified"}
    return {"status": "resent"}

@router.get("/verify/status", openapi_extra={"security": []})
def verify_status(email: str, db: Session = Depends(get_db)):
    return JSONResponse({"verified": is_user_verified(db, email)})

@router.get("/verify/confirm", response_class=HTMLResponse, openapi_extra={"security": []})
def verify_confirm(request: Request, token: str, db: Session = Depends(get_db)):
    try:
        user_id = confirm_verification_token(db, token)
    except Exception:
        # Fallback bei unerwarteten DB/Template-Fehlern
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=500)

    if not user_id:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)

    return templates.TemplateResponse("verify_success.html", {"request": request}, status_code=200)
