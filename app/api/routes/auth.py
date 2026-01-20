# app/api/routes/auth.py
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.repositories.user_repo import get_by_email
from app.schemas.auth import LoginIn, RegisterIn, UserOut
from app.schemas.mfa import MfaChallengeOut, MfaVerifyIn
from app.services import mfa_service
from app.services.auth_service import login_user, register_user, verify_login
from app.services.email_verification_service import (
    confirm_verification_token,
    is_user_verified,
    resend_verification_email,
)
from app.services.password_reset_service import complete_password_reset, start_password_reset

# ---- Option A / B: LoginOut aliasieren ----
try:
    from app.schemas.auth import LoginOut  # type: ignore
except Exception:
    from app.schemas.auth import TokenOut as LoginOut  # type: ignore

router = APIRouter(tags=["Auth"])

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _get_user_by_identifier(db: Session, identifier: str) -> Optional[User]:
    ident = (identifier or "").strip()
    if not ident:
        return None
    user = db.query(User).filter(or_(User.email == ident, User.username == ident)).first()
    if user:
        return user
    return get_by_email(db, ident) or get_by_email(db, ident.lower())


def _issue_login_after_mfa(db: Session, user: User):
    if not bool(user.is_verified):
        raise HTTPException(status_code=403, detail="Account not verified")

    for mod_name, fn_name in [
        ("app.services.auth_service", "issue_login_for_user"),
        ("app.services.auth_service", "issue_login"),
        ("app.services.auth_service", "issue_tokens_for_user"),
        ("app.services.auth_service", "create_token_for_user"),
        ("app.services.auth_service", "create_access_token_for_user"),
    ]:
        try:
            mod = __import__(mod_name, fromlist=[fn_name])
            fn = getattr(mod, fn_name, None)
            if callable(fn):
                return fn(db, user)  # type: ignore[misc]
        except Exception:
            pass

    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        raise HTTPException(status_code=500, detail="SECRET_KEY not configured")

    minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60") or "60")
    exp = datetime.utcnow() + timedelta(minutes=minutes)
    payload = {"sub": str(user.id), "exp": exp}

    token: Optional[str] = None
    alg = os.getenv("JWT_ALGORITHM", "HS256")

    try:
        from jose import jwt as jose_jwt  # type: ignore

        token = jose_jwt.encode(payload, secret, algorithm=alg)
    except Exception:
        try:
            import jwt as pyjwt  # type: ignore

            token = pyjwt.encode(payload, secret, algorithm=alg)
        except Exception:
            token = None

    if not token:
        raise HTTPException(status_code=500, detail="Token issuance failed")

    return {"token": token}


def _issue_login(
    db: Session,
    user: User,
    identifier: Optional[str] = None,
    password: Optional[str] = None,
):
    if identifier is not None and password is not None:
        res = login_user(db, identifier=identifier, password=password)
        if res == "NOT_VERIFIED":
            raise HTTPException(status_code=403, detail="Account not verified")
        if res is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return res
    return _issue_login_after_mfa(db, user)


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
        return register_user(
            db,
            username=body.username,
            email=body.email,
            password=body.password,
        )
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
    response_model=Union[LoginOut, MfaChallengeOut],
    openapi_extra={"security": []},
)
def api_login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    pre = verify_login(db, identifier=body.identifier, password=body.password)
    if pre is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if pre == "NOT_VERIFIED":
        raise HTTPException(status_code=403, detail="Account not verified")

    user = _get_user_by_identifier(db, body.identifier)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if bool(getattr(user, "mfa_enabled", False)) and (getattr(user, "mfa_method", None) or "email") == "email":
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        try:
            row = mfa_service.create_and_send_login_code(db, int(user.id), user.email, ip, ua)
        except RuntimeError as ex:
            raise HTTPException(status_code=503, detail=str(ex))
        return MfaChallengeOut(challenge_id=str(row.id))

    return _issue_login(db, user, identifier=body.identifier, password=body.password)


@router.post("/mfa/verify", openapi_extra={"security": []})
def mfa_verify(payload: MfaVerifyIn, request: Request, db: Session = Depends(get_db)):
    from app.models.mfa_code import MFACode

    try:
        cid: object = int(payload.challenge_id)
    except Exception:
        cid = payload.challenge_id

    row = db.query(MFACode).filter(MFACode.id == cid, MFACode.purpose == "login").first()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid challenge")

    ok = mfa_service.verify_code(db, int(row.user_id), str(row.id), "login", payload.code)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid code")

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid user")

    return _issue_login(db, user)


@router.post("/mfa/verify-web", openapi_extra={"security": []})
def mfa_verify_web(
    request: Request,
    code: str = Form(...),
    challenge_id: str = Form(...),
    next: str = Form("/dashboard"),
    db: Session = Depends(get_db),
):
    from app.models.mfa_code import MFACode

    try:
        cid: object = int(challenge_id)
    except Exception:
        cid = challenge_id

    row = db.query(MFACode).filter(MFACode.id == cid, MFACode.purpose == "login").first()
    if not row:
        return templates.TemplateResponse(
            "mfa_verify.html",
            {"request": request, "challenge_id": challenge_id, "next": next, "error": "Ungültiger Code.."},
            status_code=400,
        )

    ok = mfa_service.verify_code(db, int(row.user_id), str(row.id), "login", code)
    if not ok:
        return templates.TemplateResponse(
            "mfa_verify.html",
            {"request": request, "challenge_id": challenge_id, "next": next, "error": "Ungültiger Code.."},
            status_code=401,
        )

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        return templates.TemplateResponse(
            "mfa_verify.html",
            {"request": request, "challenge_id": challenge_id, "next": next, "error": "Ungültiger Benutzer.."},
            status_code=400,
        )

    data = _issue_login(db, user)

    redirect_to = next or "/dashboard"
    if not redirect_to.startswith("/"):
        redirect_to = "/dashboard"

    resp = RedirectResponse(url=redirect_to, status_code=303)
    resp.set_cookie(
        key="access_token",
        value=data["token"],
        httponly=True,
        samesite="lax",
        path="/",
        secure=False,
    )
    return resp


@router.post("/logout", status_code=204)
def api_logout(response: Response):
    response.delete_cookie(
        key="access_token",
        path="/",
        samesite="lax",
        secure=False,
        httponly=True,
    )
    response.status_code = 204
    return response


@router.post("/logout-web", include_in_schema=False)
@router.get("/logout-web", include_in_schema=False)
async def logout_web(request: Request):
    try:
        request.session.clear()
    except Exception:
        pass

    accept = (request.headers.get("accept") or "").lower()
    xrw = (request.headers.get("x-requested-with") or "").lower()
    wants_json = ("application/json" in accept) or (xrw == "xmlhttprequest")

    if wants_json:
        resp = JSONResponse({"status": "ok"}, status_code=200)
    else:
        resp = RedirectResponse(url="/auth/login-web", status_code=303)

    resp.delete_cookie(
        key="access_token",
        path="/",
        samesite="lax",
        secure=False,
        httponly=True,
    )
    return resp


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
            {"request": request, "user": None, "error": "E-Mail/Benutzername oder Passwort falsch.", "bad_login": True},
            status_code=401,
        )
    if pre == "NOT_VERIFIED":
        u = get_by_email(db, identifier) or get_by_email(db, identifier.lower())
        email = u.email if u else identifier
        return RedirectResponse(url=f"/auth/verify/sent?email={email}", status_code=303)

    user = _get_user_by_identifier(db, identifier)
    if user and bool(getattr(user, "mfa_enabled", False)) and (getattr(user, "mfa_method", None) or "email") == "email":
        redirect_to = request.query_params.get("next") or "/dashboard"
        if not redirect_to.startswith("/"):
            redirect_to = "/dashboard"

        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        try:
            row = mfa_service.create_and_send_login_code(db, int(user.id), user.email, ip, ua)
        except RuntimeError:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "user": None,
                    "error": "E-Mail-Versand nicht konfiguriert. Bitte Admin kontaktieren.",
                    "bad_login": True,
                },
                status_code=503,
            )

        return templates.TemplateResponse(
            "mfa_verify.html",
            {"request": request, "challenge_id": str(row.id), "next": redirect_to, "error": None},
            status_code=200,
        )

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
        secure=False,
    )
    return resp


@router.post("/login-web-safe", openapi_extra={"security": []})
def login_submit_safe(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    pre = verify_login(db, identifier=identifier, password=password)
    if pre == "NOT_VERIFIED":
        return RedirectResponse(url=f"/auth/verify/sent?email={identifier}", status_code=303)
    if pre is None:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Login fehlgeschlagen", "bad_login": True},
            status_code=401,
        )

    user = _get_user_by_identifier(db, identifier)
    if user and bool(getattr(user, "mfa_enabled", False)) and (getattr(user, "mfa_method", None) or "email") == "email":
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        try:
            row = mfa_service.create_and_send_login_code(db, int(user.id), user.email, ip, ua)
        except RuntimeError:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "user": None,
                    "error": "E-Mail-Versand nicht konfiguriert. Bitte Admin kontaktieren.",
                    "bad_login": True,
                },
                status_code=503,
            )

        return templates.TemplateResponse(
            "mfa_verify.html",
            {"request": request, "challenge_id": str(row.id), "next": "/dashboard", "error": None},
            status_code=200,
        )

    res = login_user(db, identifier=identifier, password=password)
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
    return templates.TemplateResponse("register.html", {"request": request, "user": None, "error": None})


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

    return RedirectResponse(url=f"/auth/verify/sent?email={email}", status_code=303)


@router.get("/password-reset", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_request_form(request: Request):
    return templates.TemplateResponse("password_reset_request.html", {"request": request, "sent": False})


@router.post("/password-reset", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_request_submit(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    start_password_reset(db, email)
    return templates.TemplateResponse("password_reset_request.html", {"request": request, "sent": True})


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
    return templates.TemplateResponse("password_reset_confirm.html", {"request": request, "token": token, "ok": None, "error": None})


@router.post("/password-reset/confirm", response_class=HTMLResponse, openapi_extra={"security": []})
def reset_confirm_submit(request: Request, token: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    ok = complete_password_reset(db, token, password)
    if ok:
        return RedirectResponse(url="/auth/login-web?reset=ok", status_code=303)

    return templates.TemplateResponse(
        "password_reset_confirm.html",
        {"request": request, "token": token, "ok": False, "error": "Token ungueltig/abgelaufen oder Passwort-Policy verletzt."},
        status_code=400,
    )


@router.get("/verify/sent", response_class=HTMLResponse, openapi_extra={"security": []})
def verify_sent(request: Request, email: str = Query(...)):
    return templates.TemplateResponse("verify_sent.html", {"request": request, "email": email})


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
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=500)

    if not user_id:
        return templates.TemplateResponse("verify_failed.html", {"request": request}, status_code=400)

    return templates.TemplateResponse("verify_success.html", {"request": request}, status_code=200)
