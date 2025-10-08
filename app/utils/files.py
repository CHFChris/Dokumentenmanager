import os, hashlib
from typing import BinaryIO

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def save_stream_to_file(file_obj: BinaryIO, target_path: str, chunk_size: int = 1024 * 1024) -> int:
    total = 0
    with open(target_path, "wb") as f:
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    return total

def sha256_of_stream(fobj: BinaryIO, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    while True:
        chunk = fobj.read(chunk_size)
        if not chunk:
            break
        h.update(chunk)
    fobj.close()
    return h.hexdigest()
