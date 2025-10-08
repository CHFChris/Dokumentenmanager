# app/web/routes_web.py
from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user_web, CurrentUser
from app.services.auth_service import register_user, login_user
from app.services.document_service import list_documents, upload_document, remove_document

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

# --------- Auth Seiten ---------
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    try:
        data = login_user(db, email, password)  # -> {"token":..., "user":{...}}
    except ValueError:
        return templates.TemplateResponse("login.html", {"request": request, "error": "E-Mail oder Passwort falsch"})
    resp = RedirectResponse(url="/", status_code=HTTP_302_FOUND)
    # Cookie setzen (httpOnly, keine JS nötig)
    resp.set_cookie("access_token", data["token"], httponly=True, samesite="lax")
    return resp

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@router.post("/register", response_class=HTMLResponse)
def register_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    try:
        register_user(db, email, password)
    except ValueError:
        return templates.TemplateResponse("register.html", {"request": request, "error": "E-Mail bereits vergeben"})
    # Nach Registrierung direkt zum Login
    return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)

@router.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    resp.delete_cookie("access_token")
    return resp

# --------- Dashboard / Dateien ---------
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, q: str | None = None, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user_web)):
    data = list_documents(db, user.id, q, 50, 0)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "items": data.items,
        "total": data.total,
        "q": q or ""
    })

@router.post("/upload-web")
def upload_web(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user_web)):
    upload_document(db, user.id, file.filename, file.file)
    return RedirectResponse(url="/", status_code=HTTP_302_FOUND)

@router.get("/delete/{doc_id}")
def delete_web(doc_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user_web)):
    ok = remove_document(db, user.id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return RedirectResponse(url="/", status_code=HTTP_302_FOUND)
