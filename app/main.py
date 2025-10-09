# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.routes import auth as auth_routes
from app.api.routes import files as files_routes
from app.web.routes_web import router as web_router  # <-- NEU

app = FastAPI(title=settings.APP_NAME)

# CORS nur für API nötig (Frontend-HTML kommt ja jetzt aus demselben Server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# (optional) Static für Logos/CSS, falls du willst:
# app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# API
app.include_router(auth_routes.router)
app.include_router(files_routes.router)

# WEB
from app.web.routes_web import router as web_router
app.include_router(web_router)
