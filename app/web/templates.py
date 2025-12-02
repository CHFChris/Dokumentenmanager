# app/web/templates.py
from pathlib import Path
from fastapi.templating import Jinja2Templates

# Basisverzeichnis: app/web
BASE_DIR = Path(__file__).resolve().parent

# Ordner, in dem deine Jinja2-HTML-Templates liegen
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
