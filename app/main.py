# app/main.py
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse, FileResponse, Response
from fastapi.security import HTTPBearer
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.db.database import init_models
from app.services.trash_service import start_trash_cleanup_task

from app.api.routes import (
    auth as auth_routes,
    account as account_routes,
    files as files_routes,
    users as users_routes,
    upload as upload_routes,
    categories as categories_routes,
    categories_api as categories_api_routes,
    profile as profile_routes,
)

from app.web import routes_web

app = FastAPI(
    title="Dokumentenmanager",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "web" / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def on_startup() -> None:
    init_models()
    start_trash_cleanup_task()


from app.api.routes import debug_ocr
app.include_router(debug_ocr.router)


# JSON-APIs
app.include_router(auth_routes.router, prefix="/auth")
app.include_router(account_routes.router)  # /account/...
app.include_router(files_routes.router, prefix="/files")
app.include_router(users_routes.router, prefix="/users")
app.include_router(profile_routes.router)

app.include_router(upload_routes.router)
app.include_router(categories_api_routes.router)

# Web (HTML / Jinja)
app.include_router(categories_routes.router)
app.include_router(routes_web.router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico_path = STATIC_DIR / "favicon.ico"
    if ico_path.exists():
        return FileResponse(str(ico_path))
    return Response(status_code=204)


@app.middleware("http")
async def redirect_unauthenticated_html(request: Request, call_next):
    response = await call_next(request)

    accept = request.headers.get("accept", "")
    path = request.url.path

    if (
        response.status_code == 401
        and "text/html" in accept
        and request.method == "GET"
        and not path.startswith("/auth")
        and not path.startswith("/docs")
        and not path.startswith("/openapi")
        and not path.startswith("/static")
    ):
        return RedirectResponse(url=f"/auth/login-web?next={path}", status_code=303)

    return response


security = HTTPBearer()


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Mein API",
        version="1.0.0",
        description="Dokumentenmanager API",
        routes=app.routes,
    )

    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    openapi_schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
