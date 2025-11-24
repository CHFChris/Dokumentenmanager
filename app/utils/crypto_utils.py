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

def encrypt_text(plaintext: str) -> str:
    """
    Verschlüsselt einen Text mit Fernet und liefert einen String,
    der direkt in ein TEXT/VARCHAR-Feld der DB gespeichert werden kann.
    """
    if plaintext is None:
        return ""
    token = fernet.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(token: str) -> str:
    """
    Entschlüsselt einen verschlüsselten Text.
    Falls der Wert noch unverschlüsselt (Altbestand) ist oder kaputt,
    wird der Originalwert zurückgegeben, damit nichts crasht.
    """
    if token is None:
        return ""
    try:
        data = fernet.decrypt(token.encode("utf-8"))
        return data.decode("utf-8")
    except Exception:
        # Altbestand (noch Klartext) oder defekte Daten
        return token
