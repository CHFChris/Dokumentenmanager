from fastapi import FastAPI
from fastapi.responses import RedirectResponse   # ✅ Import hinzugefügt
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth as auth_routes, files as files_routes, users as users_routes
from app.web import routes_web

app = FastAPI()

# API-Router
app.include_router(auth_routes.router, prefix="/auth")
app.include_router(files_routes.router, prefix="/files")
app.include_router(users_routes.router, prefix="/users")

# WEB-Router (Jinja-Seiten)
app.include_router(routes_web.router)

# Falls du statische Assets hast
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# Root immer zum Dashboard weiterleiten
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard", status_code=302)

# app/main.py (Zusatz)
from starlette.requests import Request
from fastapi.responses import RedirectResponse

@app.middleware("http")
async def redirect_unauthenticated_html(request: Request, call_next):
    response = await call_next(request)
    # Nur für HTML-Seiten (Browser), nur GET, und nicht für Auth/Docs
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
        # Optional: gewünschte Zielseite in "next" mitgeben
        return RedirectResponse(url=f"/auth/login-web?next={path}", status_code=303)
    return response
