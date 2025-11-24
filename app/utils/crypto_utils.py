# app/utils/crypto_utils.py
from cryptography.fernet import Fernet
from app.core.config import settings


# Settings-Feld: files_fernet_key kommt aus .env (BASE64-String)
# FILES_FERNET_KEY=...
fernet = Fernet(settings.files_fernet_key.encode())


def encrypt_bytes(data: bytes) -> bytes:
    return fernet.encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return fernet.decrypt(token)
