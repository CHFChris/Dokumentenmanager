# app/main.py
from __future__ import annotations

# --- Framework / Utils ---
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi

# --- DB Bootstrap ---
from app.db.database import init_models  # Base/engine nur nötig, wenn du create_all nutzen willst

# --- API-Router (JSON) ---
from app.api.routes import (
    auth as auth_routes,
    files as files_routes,
    users as users_routes,
    upload as upload_routes,
)

# --- Web-Router (Jinja-Templates) ---
from app.web import routes_web


# =============================================================================
# 🚀 App-Instanz
# =============================================================================
app = FastAPI(
    title="Dokumentenmanager",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)


# =============================================================================
# 🗂️ Static Assets (CSS/JS/Images)
# =============================================================================
# Mount /static -> app/web/static
APP_DIR = Path(__file__).resolve().parent          # .../app
STATIC_DIR = APP_DIR / "web" / "static"            # .../app/web/static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# =============================================================================
# 🧱 Startup: Models registrieren (und optional Tabellen anlegen)
# =============================================================================
@app.on_event("startup")
def on_startup() -> None:
    # Registriert alle SQLAlchemy-Models (Import-Seite)
    init_models()
    # Falls KEIN Alembic genutzt wird:
    # from app.db.database import Base, engine
    # Base.metadata.create_all(bind=engine)


# =============================================================================
# 🔌 Router registrieren
# =============================================================================
# JSON-APIs
app.include_router(auth_routes.router, prefix="/auth")
app.include_router(files_routes.router, prefix="/files")
app.include_router(users_routes.router, prefix="/users")
app.include_router(upload_routes.router)  # /upload

# Web (HTML/Jinja)
app.include_router(routes_web.router)


# =============================================================================
# 🏠 Root → Dashboard
# =============================================================================
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


# =============================================================================
# 🔐 Middleware: bei 401 auf HTML-Seiten zum Login umleiten
# =============================================================================
@app.middleware("http")
async def redirect_unauthenticated_html(request: Request, call_next):
    """
    - JSON-Clients erhalten weiter 401.
    - HTML-GETs (ohne /auth, /docs, /openapi, /static) werden auf Login umgeleitet.
    """
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


# =============================================================================
# 📜 OpenAPI: Bearer-Auth global aktivieren (Swagger 🔒 Button)
# =============================================================================
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

    # Global Security → einzelne Endpoints können via openapi_extra={"security": []} opt-outen
    openapi_schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
