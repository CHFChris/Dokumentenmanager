# app/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi

from app.db.database import init_models, Base, engine
# API-Router
from app.api.routes import (
    auth as auth_routes,
    files as files_routes,
    users as users_routes,
    upload as upload_routes,
)
# WEB-Router (Jinja)
from app.web import routes_web


app = FastAPI()


# ------------------------------
# 🔧 Startup: Models registrieren (+ optional Tabellen anlegen)
# ------------------------------
@app.on_event("startup")
def on_startup():
    # Registriert alle Models (User, PasswordResetToken, …)
    init_models()

    # Nur verwenden, wenn du KEIN Alembic nutzt:
    # Base.metadata.create_all(bind=engine)
    # (Wenn Alembic: Migrationen laufen lassen, create_all NICHT benutzen.)


# ------------------------------
# 📡 API-Router registrieren
# ------------------------------
app.include_router(auth_routes.router, prefix="/auth")
app.include_router(files_routes.router, prefix="/files")
app.include_router(users_routes.router, prefix="/users")
app.include_router(upload_routes.router)  # -> aktiviert /upload

# ------------------------------
# 🧭 Web-Router (Jinja2-Seiten)
# ------------------------------
app.include_router(routes_web.router)

# ------------------------------
# 🖼️ Statische Dateien (CSS/JS/Assets)
# ------------------------------
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# ------------------------------
# 🏠 Root-Route → Weiterleitung zum Dashboard
# ------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard", status_code=302)

# ------------------------------
# 🛡️ Middleware: 401 bei HTML → Login (mit ?next=…)
# ------------------------------
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

# ==============================
# 🔒 OpenAPI-Security (Authorize-Button)
# ==============================
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
    # Global: Swagger zeigt 🔒 an allen Endpoints
    openapi_schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
