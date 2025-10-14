# app/api/routes/auth.py
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.auth import RegisterIn, LoginIn, UserOut
from app.services.auth_service import register_user, login_user, verify_login

router = APIRouter()

# Pfad: .../app/api/routes/auth.py  -> parents[2] == .../app
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# --------------------
# API: JSON Endpunkte
# --------------------
@router.post("/register", response_model=UserOut, status_code=201)
def api_register(body: RegisterIn, db: Session = Depends(get_db)):
    try:
        user = register_user(db, body.email, body.password)
        return user
    except ValueError as ex:
        if str(ex) == "USER_EXISTS":
            raise HTTPException(status_code=409, detail="USER_EXISTS")
        raise

@router.post("/login")
def api_login(body: LoginIn, db: Session = Depends(get_db)):
    # liefert {"token": "...", "user": {...}}
    return login_user(db, body.email, body.password)

@router.post("/logout", status_code=204)
def api_logout(response: Response):
    response.delete_cookie("access_token")
    return Response(status_code=204)


# --------------------
# WEB: HTML-Formulare
# --------------------
@router.get("/login-web", response_class=HTMLResponse)
def login_form(request: Request):
    # user=None -> in base.html keine App-Navigation
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "user": None, "error": None},
    )

@router.post("/login-web")
def login_submit(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = verify_login(db, email, password)
    if not user:
        # zurück zur Login-Seite mit Fehler
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "user": None, "error": "E-Mail oder Passwort falsch."},
            status_code=401,
        )

    # Token erzeugen und als httpOnly-Cookie setzen
    data = login_user(db, email, password)  # {"token":..., "user":...}
    redirect_to = request.query_params.get("next") or "/dashboard"
    resp = RedirectResponse(url=redirect_to, status_code=303)
    resp.set_cookie(
        key="access_token",
        value=data["token"],
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp

@router.get("/register-web", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "user": None, "error": None},
    )

@router.post("/register-web")
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

    # nach erfolgreicher Registrierung direkt einloggen
    data = login_user(db, email, password)
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(key="access_token", value=data["token"], httponly=True, samesite="lax", path="/")
    return resp

@router.post("/logout-web")
def logout_web():
    resp = RedirectResponse(url="/auth/login-web", status_code=303)
    resp.delete_cookie("access_token")
    return resp
