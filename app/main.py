import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import auth as auth_routes
from app.api.routes import users as users_routes
from app.api.routes import files as files_routes
from app.api.routes import duplicates as dup_routes
from app.utils.file_storage import ensure_base_dir

app = FastAPI(title=settings.APP_NAME, version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(users_routes.router)
app.include_router(files_routes.router)
app.include_router(dup_routes.router)

@app.on_event("startup")
def startup():
    ensure_base_dir()
    os.makedirs(settings.FILES_DIR, exist_ok=True)
