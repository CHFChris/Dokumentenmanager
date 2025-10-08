import os
from pathlib import Path
from typing import BinaryIO
from app.core.config import settings

BASE = Path(settings.FILES_DIR)

def ensure_base_dir() -> None:
    BASE.mkdir(parents=True, exist_ok=True)

def join_path(user_id: int, filename: str) -> Path:
    safe_name = filename.replace("..", "_")
    return BASE / str(user_id) / safe_name

def save_file(user_id: int, filename: str, data: BinaryIO) -> str:
    ensure_base_dir()
    target = join_path(user_id, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f:
        f.write(data.read())
    return str(target)
